"""Command-line interface — the whole workflow, headless and scriptable.

This CLI runs the same engine as the GUI, headless — which makes big
batches fast (no window in the way) and lets you script a library
clean-up. The quickest taste is the one-shot form::

    mp3csvtagger run --folder ~/Music --csv tags.csv \
        --match "Lead Performer" --write Title,Genre --dry-run

or drive everything from a saved project (the same file the GUI opens)::

    mp3csvtagger new        project.mp3p.json
    mp3csvtagger add-files  project.mp3p.json --folder ~/Music
    mp3csvtagger add-csv    project.mp3p.json tags.csv \
        --roles "Lead Performer=Match,Title=Write,Genre=Write"
    mp3csvtagger preview    project.mp3p.json --out preview.csv
    mp3csvtagger apply      project.mp3p.json

More commands: ``undo`` (restore a run from its tag snapshot), ``export``
(library → CSV), ``from-filename`` (capture tags from names/paths),
``report`` (duplicates + spelling variants), ``presets`` (saved column
roles) and ``lookup`` (opt-in MusicBrainz fill of empty tags). Each has
its own ``--help``.

Roles are ``Match``, ``Write`` or ``Skip`` (see :class:`.project.Role`).
"""

from __future__ import annotations

import argparse
import os
import sys

from . import __version__, musicbrainz, presets, undo
from .apply import apply_preview, write_preview_csv
from .filename_tags import capture_for_file
from .library_export import append_library_csv, write_library_csv
from .library_report import (
    duplicate_groups,
    render_csv_report,
    render_text_report,
    variant_groups,
)
from .mp3files import scan
from .preview import add_value_layer, build_preview, empty_preview
from .project import Project, Role

_ROLE_NAMES = {role.name.lower(): int(role) for role in Role}


def _parse_roles(spec: str) -> dict[str, int]:
    """Parse ``"Title=Write,Lead Performer=Match"`` into {column: role int}."""
    roles: dict[str, int] = {}
    for part in (spec or "").split(","):
        part = part.strip()
        if not part:
            continue
        if "=" not in part:
            raise SystemExit(f"Bad --roles entry {part!r} (expected Column=Role)")
        column, role = part.split("=", 1)
        key = role.strip().lower()
        if key not in _ROLE_NAMES:
            raise SystemExit(f"Unknown role {role!r} (use Match, Write or Skip)")
        roles[column.strip()] = _ROLE_NAMES[key]
    return roles


def _apply_roles(project_entry, roles: dict[str, int]) -> None:
    for tag in project_entry.tags:
        if tag.name in roles:
            tag.role = roles[tag.name]


def _print_summary(preview, result=None) -> None:
    print(f"Files scanned : {preview.files_scanned}")
    print(f"Files matched : {preview.files_matched}")
    print(f"Tag changes   : {preview.total_changes}")
    for error in preview.scan_errors:
        print(f"  scan error: {error}")
    if result is not None:
        print(f"Files written : {result.files_written} ({result.tags_written} tags)")
        print(f"Files unchanged: {result.files_unchanged}")
        for error in result.errors:
            print(f"  write error: {error}")
        if result.log_file:
            print(f"Change log    : {result.log_file}")
        if result.undo_file:
            print(f"Undo snapshot : {result.undo_file}")


def _progress_printer(kind: str):
    def _progress(done, total, path):
        if done == total or done % 100 == 0:
            print(f"  {kind} {done}/{total}", file=sys.stderr)

    return _progress


def cmd_new(args) -> int:
    """Create an empty project file and report it."""
    Project().save(args.project)
    print(f"Created {args.project}")
    return 0


def cmd_add_files(args) -> int:
    """Add --folder/--file paths to a project and save it."""
    project = Project.load(args.project)
    for folder in args.folder or []:
        project.add_mp3_path(folder)
    for file in args.file or []:
        project.add_mp3_path(file)
    project.save(args.project)
    print(f"Project now has {len(project.mp3_paths)} MP3 path(s)")
    return 0


def cmd_add_csv(args) -> int:
    """Add a CSV layer to a project (roles/preset applied) and save it."""
    project = Project.load(args.project)
    entry = project.add_csv_file(args.csv)
    _apply_roles(entry, _parse_roles(args.roles))
    if args.preset:
        # A preset is applied after --roles, so it wins where both name a
        # column: presets are the deliberate, saved setup.
        preset = presets.load_preset(args.preset)
        changed = presets.apply_preset(entry, preset)
        print(f"Applied preset {preset.name!r} to {changed} column(s)")
    if args.exclude:
        entry.included = False
    project.save(args.project)
    print(f"Added {args.csv} with columns: {', '.join(t.name for t in entry.tags)}")
    return 0


def _scan_args(args) -> list:
    """Scan the --folder/--file paths shared by several commands."""
    paths = list(args.folder or []) + list(args.file or [])
    if not paths:
        raise SystemExit("Give at least one --folder or --file")
    return scan(paths, progress=_progress_printer("scan"))


def cmd_undo(args) -> int:
    """Restore one run from its .undo snapshot; print the outcome."""
    result = undo.undo_run(args.undo_file, force=args.force)
    for message in result.messages:
        print(message)
    print(f"Restored: {result.restored}  Skipped: {len(result.skipped)}  "
          f"Errors: {len(result.errors)}")
    return 1 if result.errors else 0


def cmd_export(args) -> int:
    """Export the scanned library's tags to a CSV file.

    Without ``--append`` the target CSV is created (or overwritten).
    With ``--append`` the scan is merged into the existing CSV at
    ``--out``: see :func:`library_export.append_library_csv` for the
    merge rules.
    """
    if args.project:
        project = Project.load(args.project)
        files = scan(project.mp3_paths, progress=_progress_printer("scan"))
    else:
        files = _scan_args(args)
    if getattr(args, "append", False):
        if not os.path.exists(args.out):
            raise SystemExit(
                f"--append needs an existing CSV to merge into; "
                f"{args.out} does not exist. Export without --append first."
            )
        summary = append_library_csv(files, args.out)
        print(f"Appended a scan of {summary.files_scanned} file(s) to {args.out}")
        print(f"Rows added: {summary.rows_added}  "
              f"Rows updated: {summary.rows_updated}  "
              f"Rows kept: {summary.rows_kept}")
        if summary.columns_added:
            print(f"Columns added: {', '.join(summary.columns_added)}")
        if summary.warning:
            print(f"Warning: {summary.warning}")
        return 0
    columns = write_library_csv(files, args.out)
    print(f"Exported {len(files)} file(s), {len(columns)} column(s) to {args.out}")
    print(f"Columns: {', '.join(columns)}")
    return 0


def _finish_virtual_run(args, preview, files, source: str) -> int:
    """Shared tail for from-filename / lookup: show, then apply if asked."""
    _print_summary(preview)
    for row in preview.rows:
        for cell in row.cells.values():
            if cell.changed:
                print(f"{row.filename}  {cell.tag_name}: "
                      f"{cell.old_value!r} -> {cell.value!r}")
    if getattr(args, "out", ""):
        write_preview_csv(preview, args.out)
        print(f"Preview written to {args.out}")
    if args.apply:
        result = apply_preview(
            preview,
            log_folder=args.log_folder or os.path.expanduser("~/mp3tagging"),
            progress=_progress_printer("write"),
        )
        _print_summary(preview, result)
        if result.undo_file:
            print(f"Undo snapshot : {result.undo_file}")
        return 1 if result.errors else 0
    print(f"Dry run — re-run with --apply to write these {source} values.")
    return 0


def cmd_from_filename(args) -> int:
    """Capture tags from names/paths; dry-run unless --apply."""
    files = _scan_args(args)
    root = args.root or (args.folder[0] if args.folder and len(args.folder) == 1 else None)
    values: dict[str, dict[str, str]] = {}
    for mp3 in files:
        captured = capture_for_file(
            args.pattern, mp3.path, root=root, use_path=args.use_path
        )
        if captured:
            values[mp3.path] = captured
    print(f"Pattern matched {len(values)} of {len(files)} file(s)")
    preview = empty_preview(files)
    add_value_layer(preview, files, values, "filename pattern")
    return _finish_virtual_run(args, preview, files, "filename")


def cmd_report(args) -> int:
    """Print the duplicates + spelling-variants report."""
    files = _scan_args(args)
    duplicates = duplicate_groups(files)
    tag_names = [t.strip() for t in (args.tags or "").split(",") if t.strip()] or [
        "Lead Performer", "Album", "Genre",
    ]
    variants = []
    for tag_name in tag_names:
        variants.extend(variant_groups(files, tag_name))
    text = render_text_report(duplicates, variants)
    print(text)
    if args.out:
        # The extension chooses the format: .csv gets one row per
        # affected file for spreadsheet use; anything else gets the
        # same text report that was printed.
        if args.out.lower().endswith(".csv"):
            text = render_csv_report(duplicates, variants)
        with open(args.out, "w", encoding="utf-8") as handle:
            handle.write(text)
        print(f"Report written to {args.out}")
    return 0


def cmd_presets(args) -> int:
    """List built-in and saved role presets."""
    builtin_names = {p.name for p in presets.builtin_presets()}
    for preset in presets.list_presets():
        kind = "built-in" if preset.name in builtin_names else "saved"
        roles = ", ".join(
            f"{col}={_ROLE_LABELS.get(role, role)}"
            for col, role in preset.roles.items()
        )
        print(f"{preset.name} ({kind}): {roles}")
    return 0


_ROLE_LABELS = {int(role): role.name for role in Role}


def cmd_lookup(args) -> int:
    """Fill empty tags from MusicBrainz; dry-run unless --apply."""
    if args.project:
        project = Project.load(args.project)
        files = scan(project.mp3_paths, progress=_progress_printer("scan"))
    else:
        files = _scan_args(args)
    fields = [f.strip() for f in (args.fields or "").split(",") if f.strip()] or [
        "Album", "Year", "Genre",
    ]
    print(f"Looking up missing {', '.join(fields)} on MusicBrainz "
          f"(max 1 request/second; only empty tags are filled)…")
    fills, errors = musicbrainz.fill_missing(
        files, fields, progress=_progress_printer("lookup")
    )
    for error in errors:
        print(f"  lookup error: {error}")
    print(f"Found values for {len(fills)} file(s)")
    preview = empty_preview(files)
    add_value_layer(preview, files, fills, "MusicBrainz lookup")
    return _finish_virtual_run(args, preview, files, "looked-up")


def _load_preview(args):
    project = Project.load(args.project)
    if args.log_folder:
        project.apply_log_folder = args.log_folder
    preview = build_preview(project, progress=_progress_printer("scan"))
    return project, preview


def cmd_preview(args) -> int:
    """Build a project's preview; print it or export it with --out."""
    _project, preview = _load_preview(args)
    _print_summary(preview)
    if args.out:
        write_preview_csv(preview, args.out)
        print(f"Preview written to {args.out}")
    else:
        for row in preview.rows:
            for cell in row.cells.values():
                if cell.changed:
                    print(f"{row.filename}  {cell.tag_name}: {cell.old_value!r} -> {cell.value!r}")
    return 0


def cmd_apply(args) -> int:
    """Build a project's preview and write it (unless --dry-run)."""
    project, preview = _load_preview(args)
    if args.dry_run:
        _print_summary(preview)
        print("Dry run — nothing written.")
        return 0
    result = apply_preview(
        preview,
        log_folder=project.apply_log_folder,
        progress=_progress_printer("write"),
    )
    _print_summary(preview, result)
    return 1 if result.errors else 0


def cmd_run(args) -> int:
    """One-shot: no project file, everything from flags."""
    project = Project()
    for folder in args.folder or []:
        project.add_mp3_path(folder)
    for file in args.file or []:
        project.add_mp3_path(file)
    if not project.mp3_paths:
        raise SystemExit("Give at least one --folder or --file")
    for csv_path in args.csv:
        project.add_csv_file(csv_path)
    # --match / --write / --roles apply to every CSV. For layered runs where
    # each CSV needs different roles, use --csv-roles once per --csv, in the
    # same order: the first --csv-roles belongs to the first --csv, and so on.
    match_cols = [c.strip() for c in (args.match or "").split(",") if c.strip()]
    write_cols = [c.strip() for c in (args.write or "").split(",") if c.strip()]
    extra_roles = _parse_roles(args.roles)
    per_csv_roles = [_parse_roles(spec) for spec in (args.csv_roles or [])]
    for position, entry in enumerate(project.csv_entries):
        for tag in entry.tags:
            if tag.name in match_cols:
                tag.role = int(Role.Match)
            elif tag.name in write_cols:
                tag.role = int(Role.Write)
            if tag.name in extra_roles:
                tag.role = extra_roles[tag.name]
        if position < len(per_csv_roles):
            _apply_roles(entry, per_csv_roles[position])
    if args.log_folder:
        project.apply_log_folder = args.log_folder
    preview = build_preview(project, progress=_progress_printer("scan"))
    if args.out:
        write_preview_csv(preview, args.out)
        print(f"Preview written to {args.out}")
    if args.apply:
        result = apply_preview(
            preview, log_folder=project.apply_log_folder,
            progress=_progress_printer("write"),
        )
        _print_summary(preview, result)
        return 1 if result.errors else 0
    _print_summary(preview)
    if not args.out:
        print("Dry run — re-run with --apply to write these tags.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Build the argparse parser for all sub-commands."""
    parser = argparse.ArgumentParser(
        prog="mp3csvtagger",
        description="Bulk-edit MP3 ID3 tags from CSV files (Match/Write/Skip columns).",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("new", help="create an empty project file")
    p.add_argument("project")
    p.set_defaults(func=cmd_new)

    p = sub.add_parser("add-files", help="add MP3 files/folders to a project")
    p.add_argument("project")
    p.add_argument("--folder", action="append", help="folder to scan recursively")
    p.add_argument("--file", action="append", help="a single MP3 file")
    p.set_defaults(func=cmd_add_files)

    p = sub.add_parser("add-csv", help="add a CSV layer to a project")
    p.add_argument("project")
    p.add_argument("csv")
    p.add_argument("--roles", default="", help='"Column=Role,..." e.g. "Title=Write"')
    p.add_argument("--preset", default="", help="role preset name or JSON path (applied after --roles)")
    p.add_argument("--exclude", action="store_true", help="add but leave switched off")
    p.set_defaults(func=cmd_add_csv)

    p = sub.add_parser("undo", help="restore the tags a previous apply replaced")
    p.add_argument("undo_file", help="the .undo snapshot written next to the change log")
    p.add_argument("--force", action="store_true", help="restore even if a file changed since the run")
    p.set_defaults(func=cmd_undo)

    p = sub.add_parser("export", help="export a scanned library's tags to CSV")
    p.add_argument("project", nargs="?", default="", help="project file (or use --folder/--file)")
    p.add_argument("--folder", action="append", help="folder to scan recursively")
    p.add_argument("--file", action="append", help="a single MP3 file")
    p.add_argument("--out", required=True, help="CSV file to write")
    p.add_argument("--append", action="store_true",
                   help="merge into the existing --out CSV instead of "
                        "overwriting it (rows keyed by FilePath; see the "
                        "Help topic 'Exporting your library to CSV')")
    p.set_defaults(func=cmd_export)

    p = sub.add_parser("from-filename", help="capture tag values from file names/paths")
    p.add_argument("--folder", action="append", help="folder to scan recursively")
    p.add_argument("--file", action="append", help="a single MP3 file")
    p.add_argument("--pattern", required=True, help='e.g. "{Lead Performer} - {Title}"')
    p.add_argument("--use-path", action="store_true", help="match the pattern against the path relative to --root")
    p.add_argument("--root", default="", help="root folder for --use-path (default: the single --folder)")
    p.add_argument("--log-folder", default="", help="folder for the change log + undo snapshot")
    p.add_argument("--out", default="", help="also export the preview to this CSV")
    p.add_argument("--apply", action="store_true", help="actually write (default is a dry run)")
    p.set_defaults(func=cmd_from_filename)

    p = sub.add_parser("report", help="duplicate tracks + spelling variants report")
    p.add_argument("--folder", action="append", help="folder to scan recursively")
    p.add_argument("--file", action="append", help="a single MP3 file")
    p.add_argument("--tags", default="", help='comma-separated tags for variant checks (default "Lead Performer,Album,Genre")')
    p.add_argument("--out", default="", help="also write the report to this file (.csv path = CSV format, otherwise text)")
    p.set_defaults(func=cmd_report)

    p = sub.add_parser("presets", help="list the built-in and saved role presets")
    p.set_defaults(func=cmd_presets)

    p = sub.add_parser("lookup", help="fill EMPTY tags from MusicBrainz (opt-in, online)")
    p.add_argument("project", nargs="?", default="", help="project file (or use --folder/--file)")
    p.add_argument("--folder", action="append", help="folder to scan recursively")
    p.add_argument("--file", action="append", help="a single MP3 file")
    p.add_argument("--fields", default="", help='comma-separated fields to fill (default "Album,Year,Genre")')
    p.add_argument("--log-folder", default="", help="folder for the change log + undo snapshot")
    p.add_argument("--out", default="", help="also export the preview to this CSV")
    p.add_argument("--apply", action="store_true", help="actually write (default is a dry run)")
    p.set_defaults(func=cmd_lookup)

    for name, func, helptext in (
        ("preview", cmd_preview, "build and show the preview for a project"),
        ("apply", cmd_apply, "build the preview and write the tags"),
    ):
        p = sub.add_parser(name, help=helptext)
        p.add_argument("project")
        p.add_argument("--log-folder", default="", help="folder for the change log CSV")
        if name == "preview":
            p.add_argument("--out", default="", help="also export the preview to this CSV")
        else:
            p.add_argument("--dry-run", action="store_true", help="show changes, write nothing")
        p.set_defaults(func=func)

    p = sub.add_parser("run", help="one-shot run without a project file")
    p.add_argument("--folder", action="append", help="folder to scan recursively")
    p.add_argument("--file", action="append", help="a single MP3 file")
    p.add_argument("--csv", action="append", required=True, help="a CSV layer (repeatable)")
    p.add_argument("--match", default="", help='comma-separated Match columns, e.g. "Lead Performer"')
    p.add_argument("--write", default="", help='comma-separated Write columns, e.g. "Title,Genre"')
    p.add_argument("--roles", default="", help='"Column=Role,..." applied to every CSV')
    p.add_argument("--csv-roles", action="append", default=[], help='"Column=Role,..." for one CSV; repeat once per --csv, in order')
    p.add_argument("--log-folder", default="", help="folder for the change log CSV")
    p.add_argument("--out", default="", help="also export the preview to this CSV")
    p.add_argument("--apply", action="store_true", help="actually write (default is a dry run)")
    p.set_defaults(func=cmd_run)

    p = sub.add_parser("gui", help="open the desktop app")
    p.add_argument("project", nargs="?", default="", help="project file to open")
    p.set_defaults(func=lambda a: _open_gui(a))
    return parser


def _open_gui(args) -> int:
    from .gui import main as gui_main

    return gui_main(args.project or None)


def main(argv: list[str] | None = None) -> int:
    # No arguments at all -> open the GUI, like double-clicking the old exe.
    """Entry point: no arguments opens the GUI; otherwise run a command."""
    if argv is None:
        argv = sys.argv[1:]
    if not argv:
        return _open_gui(argparse.Namespace(project=""))
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
