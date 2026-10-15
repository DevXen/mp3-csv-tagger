"""Command-line interface — the whole workflow, headless and scriptable.

The original program was GUI-only. This CLI runs the same engine, which
makes big batches fast (no window in the way) and lets you script a library
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

Roles are ``Match``, ``Write`` or ``Skip`` (see :class:`.project.Role`).
"""

from __future__ import annotations

import argparse
import os
import sys

from . import __version__
from .apply import apply_preview, write_preview_csv
from .preview import build_preview
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


def _progress_printer(kind: str):
    def _progress(done, total, path):
        if done == total or done % 100 == 0:
            print(f"  {kind} {done}/{total}", file=sys.stderr)

    return _progress


def cmd_new(args) -> int:
    Project().save(args.project)
    print(f"Created {args.project}")
    return 0


def cmd_add_files(args) -> int:
    project = Project.load(args.project)
    for folder in args.folder or []:
        project.add_mp3_path(folder)
    for file in args.file or []:
        project.add_mp3_path(file)
    project.save(args.project)
    print(f"Project now has {len(project.mp3_paths)} MP3 path(s)")
    return 0


def cmd_add_csv(args) -> int:
    project = Project.load(args.project)
    entry = project.add_csv_file(args.csv)
    _apply_roles(entry, _parse_roles(args.roles))
    if args.exclude:
        entry.included = False
    project.save(args.project)
    print(f"Added {args.csv} with columns: {', '.join(t.name for t in entry.tags)}")
    return 0


def _load_preview(args):
    project = Project.load(args.project)
    if args.log_folder:
        project.apply_log_folder = args.log_folder
    preview = build_preview(project, progress=_progress_printer("scan"))
    return project, preview


def cmd_preview(args) -> int:
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
    p.add_argument("--exclude", action="store_true", help="add but leave switched off")
    p.set_defaults(func=cmd_add_csv)

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
    if argv is None:
        argv = sys.argv[1:]
    if not argv:
        return _open_gui(argparse.Namespace(project=""))
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
