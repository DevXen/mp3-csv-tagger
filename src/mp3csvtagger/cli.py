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
``report`` (duplicates + spelling variants, plus the round-2 extensions
``--pattern`` / ``--completeness`` / ``--same-recordings``), ``presets``
(saved column roles) and ``lookup`` (opt-in MusicBrainz fill of empty
tags). Round 2 also adds ``sync-tags`` (copy tags from one library onto
its twin), ``acoustid`` (opt-in AcoustID fill of empty tags),
``fingerprint-status`` (is the ``fpcalc`` tool available?) and the
saved-job commands ``jobs``, ``job-save`` and ``job-run``. Each command
has its own ``--help``.

Roles are ``Match``, ``Write`` or ``Skip`` (see :class:`.project.Role`).
"""

from __future__ import annotations

import argparse
import json
import os
import sys

# The round-2 modules are imported as modules (not ``from``-imports of
# individual functions) so tests — and only tests — can monkeypatch a
# single function on the module, e.g. replace
# ``fingerprints.acoustid_lookup`` with a stub that proves no network
# call happened, and have the CLI pick the replacement up.
from . import __version__, fingerprints, jobs, musicbrainz, presets, sync, undo
from .apply import apply_preview, write_preview_csv
from .consistency import (
    check_consistency,
    render_consistency_csv,
    render_consistency_text,
)
from .filename_tags import capture_for_file
from .library_export import append_library_csv, write_library_csv
from .library_report import (
    album_completeness,
    duplicate_groups,
    render_completeness_text,
    render_csv_report,
    render_text_report,
    variant_groups,
)
from .mp3files import scan
from .preview import add_value_layer, build_preview, empty_preview
from .project import Project, Role
from .tags import frame_for_tag_name

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


def _split_list(spec: str) -> list[str]:
    """Split a ``"A,B"`` flag value into its stripped, non-empty parts."""
    return [part.strip() for part in (spec or "").split(",") if part.strip()]


#: Text printed wherever a fingerprint feature is asked for but the
#: external ``fpcalc`` tool is not installed. Fingerprints degrade to
#: "feature unavailable" rather than an error everywhere in the
#: program, so callers print this and carry on (or stop cleanly).
_FPCALC_MISSING = (
    "fpcalc was not detected, so audio fingerprints are unavailable. "
    "Install Chromaprint's fpcalc tool (run `fingerprint-status` for "
    "per-platform install help) and try again."
)


def cmd_report(args) -> int:
    """Print a library report; which sections depends on the flags.

    With no round-2 flag this is the original duplicates + spelling
    variants report. ``--pattern`` switches to the read-only
    tags-vs-path consistency report instead. ``--completeness`` and
    ``--same-recordings`` add their sections to the normal report, and
    ``--unify-from PATH`` (with ``--same-recordings``) turns one
    same-recording group into a preview that copies that file's tags
    onto the rest of its group — a dry run unless ``--apply`` is given.
    """
    files = _scan_args(args)

    # --- Tags-vs-path consistency (read-only; replaces the report) ---
    if getattr(args, "pattern", ""):
        result = check_consistency(
            files,
            args.pattern,
            root=getattr(args, "root", "") or None,
            use_path=not getattr(args, "filename_only", False),
        )
        text = render_consistency_text(result, args.pattern)
        print(text)
        if args.out:
            # Same rule as the plain report: .csv = CSV, else text.
            if args.out.lower().endswith(".csv"):
                text = render_consistency_csv(result)
            with open(args.out, "w", encoding="utf-8") as handle:
                handle.write(text)
            print(f"Report written to {args.out}")
        return 0

    # --- Same-recording groups (fingerprints), maybe with unify -----
    # ``groups`` stays None when fingerprints are unavailable: the
    # report then simply has no same-recordings section, rather than a
    # misleading "(none found)" under a feature that never ran.
    groups = None
    if getattr(args, "same_recordings", False) or getattr(args, "unify_from", ""):
        if fingerprints.fpcalc_path() is None:
            print(_FPCALC_MISSING)
        else:
            fps = fingerprints.fingerprints_for(
                files, progress=_progress_printer("fingerprint")
            )
            groups = fingerprints.same_recording_groups(files, fps)

    if getattr(args, "unify_from", ""):
        # _finish_virtual_run reads these attributes; give namespaces
        # built without them (older callers) the dry-run defaults.
        args.apply = getattr(args, "apply", False)
        args.log_folder = getattr(args, "log_folder", "")
        args.out = getattr(args, "out", "")
        if not groups:
            raise SystemExit(
                f"--unify-from {args.unify_from}: that file is not a "
                "member of any same-recording group (or fingerprints "
                "are unavailable), so there is nothing to unify from it."
            )
        wanted = os.path.abspath(args.unify_from)
        matches = [
            group for group in groups
            if any(os.path.abspath(path) == wanted for path in group["paths"])
        ]
        if len(matches) != 1:
            raise SystemExit(
                f"--unify-from {args.unify_from}: expected the file to "
                f"belong to exactly one same-recording group, found "
                f"{len(matches)}."
            )
        group = matches[0]
        source = next(
            mp3 for mp3 in files if os.path.abspath(mp3.path) == wanted
        )
        # Copy the source file's (non-empty) text tags to every other
        # member of its group. The values go through a virtual layer,
        # so the preview / apply / undo flow is the ordinary one.
        source_tags = {name: value for name, value in source.tags.items() if value}
        values = {
            path: dict(source_tags)
            for path in group["paths"]
            if os.path.abspath(path) != wanted
        }
        print(
            f"Unifying {len(values)} file(s) onto the tags of {source.path}"
        )
        preview = empty_preview(files)
        add_value_layer(preview, files, values, "same recordings")
        return _finish_virtual_run(args, preview, files, "unified")

    # --- The plain report, plus any requested extra sections ---------
    duplicates = duplicate_groups(files)
    tag_names = _split_list(args.tags) or [
        "Lead Performer", "Album", "Genre",
    ]
    variants = []
    for tag_name in tag_names:
        variants.extend(variant_groups(files, tag_name))
    text = render_text_report(duplicates, variants)
    if getattr(args, "completeness", False):
        text += "\n" + render_completeness_text(album_completeness(files))
    if groups is not None:
        lines = ["", "Same recordings (audio fingerprint)", "==================================="]
        if not groups:
            lines.append("  (none found)")
        for group in groups:
            lines.append(
                f"  {len(group['paths'])} file(s), "
                f"{group['duration']:.1f}s, fingerprint "
                f"{group['fingerprint'][:16]}…"
            )
            for path in group["paths"]:
                lines.append(f"    {path}")
        text += "\n".join(lines) + "\n"
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


def cmd_sync_tags(args) -> int:
    """Sync tags from a source library onto its target twin.

    Pairs the two libraries by relative path (optionally pairing the
    leftovers by audio fingerprint), prints the pairing and the
    differences, then builds the sync preview. A dry run unless
    ``--apply`` is given; applying writes through the ordinary apply
    path, so the run gets a change log and a snapshot undo.
    """
    source_files = scan([args.source], progress=_progress_printer("scan"))
    target_files = scan([args.target], progress=_progress_printer("scan"))
    plan = sync.pair_libraries(
        args.source, args.target,
        source_files=source_files, target_files=target_files,
    )
    if args.fingerprint_pairing:
        leftovers = plan.unpaired_source + plan.unpaired_target
        if fingerprints.fpcalc_path() is None:
            print(
                "Fingerprint pairing was requested, but fpcalc was not "
                "detected — the leftover files stay unpaired."
            )
        elif leftovers:
            fps = fingerprints.fingerprints_for(
                leftovers, progress=_progress_printer("fingerprint")
            )
            durations = {path: fp.duration for path, fp in fps.items()}
            plan = sync.pair_leftovers_by_fingerprint(plan, fps, durations)

    tags = _split_list(args.tags) or sync.default_sync_tags(plan, source_files)
    include_cover = not args.no_cover
    print(f"Paired files  : {len(plan.pairs)}")
    print(f"Unpaired source files ({len(plan.unpaired_source)}):")
    for path in plan.unpaired_source:
        print(f"  {path}")
    print(f"Unpaired target files ({len(plan.unpaired_target)}):")
    for path in plan.unpaired_target:
        print(f"  {path}")

    differences = sync.tag_differences(
        plan, source_files, target_files, tags, include_cover=include_cover,
    )
    print(f"Differences   : {len(differences)}")
    for diff in differences:
        print(
            f"  {os.path.basename(diff['target_path'])}  {diff['tag']}: "
            f"{diff['target_value']!r} -> {diff['source_value']!r}"
        )

    # Extracted cover images live in the log folder (they are run
    # artefacts, like the change log itself).
    cover_dir = args.log_folder or os.path.expanduser("~/mp3tagging")
    preview = sync.build_sync_preview(
        plan, source_files, target_files, tags,
        include_cover=include_cover, cover_dir=cover_dir,
    )
    return _finish_virtual_run(args, preview, target_files, "sync")


#: AcoustID result key -> the tag it can fill. Only these four tags are
#: filled, and only when the file's current value is empty: an AcoustID
#: lookup must never overwrite a tag the user already has.
_ACOUSTID_FIELDS = (
    ("Title", "title"),
    ("Lead Performer", "artist"),
    ("Album", "album"),
    ("Year", "year"),
)


def cmd_acoustid(args) -> int:
    """Fill EMPTY tags from AcoustID; dry-run unless --apply.

    Needs the user's own AcoustID API key (``--key`` or the saved
    setting). With no key the command explains where to put one and
    exits 2 *before* scanning or touching the network — a keyless
    lookup can only fail, and its failure mode should not look like a
    network problem.
    """
    api_key = (getattr(args, "key", "") or "").strip() or fingerprints.acoustid_api_key()
    if not api_key:
        print(
            "No AcoustID API key is set, so no lookup was made.\n"
            "AcoustID lookups use your own free API key: pass --key KEY, "
            "or save the key once in the desktop app's Setup tab (it is "
            "stored locally in ~/.mp3csvtagger/settings.json)."
        )
        return 2
    files = _scan_args(args)
    if fingerprints.fpcalc_path() is None:
        print(_FPCALC_MISSING)
        return 0
    fills: dict[str, dict[str, str]] = {}
    for mp3 in files:
        fingerprint = fingerprints.fingerprint_file(mp3.path)
        if fingerprint is None:
            print(f"  could not fingerprint {mp3.path} — skipped")
            continue
        try:
            matches = fingerprints.acoustid_lookup(fingerprint, api_key)
        except Exception as exc:
            print(f"  lookup error for {mp3.path}: {exc}")
            continue
        if not matches:
            continue
        best = matches[0]  # acoustid_lookup sorts by score, best first
        values: dict[str, str] = {}
        for tag_name, result_key in _ACOUSTID_FIELDS:
            frame = frame_for_tag_name(tag_name)
            if mp3.value_for(tag_name, frame).strip():
                continue  # only EMPTY tags are filled, ever
            value = best.get(result_key)
            if value not in (None, ""):
                values[tag_name] = str(value)
        if values:
            fills[mp3.path] = values
    print(f"Found values for {len(fills)} file(s)")
    preview = empty_preview(files)
    add_value_layer(preview, files, fills, "AcoustID lookup")
    return _finish_virtual_run(args, preview, files, "AcoustID")


def cmd_fingerprint_status(args) -> int:
    """Report whether fpcalc is available, and the cache's state."""
    path = fingerprints.fpcalc_path()
    if path:
        print(f"fpcalc: {path}")
    else:
        print("fpcalc: not detected")
        print("Install Chromaprint's fpcalc tool to enable fingerprints:")
        print("  Linux:   apt install libchromaprint-tools")
        print("  macOS:   brew install chromaprint")
        print("  Windows: download fpcalc from https://acoustid.org")
    cache = fingerprints.cache_path()
    entries = 0
    try:
        with open(cache, encoding="utf-8") as handle:
            data = json.load(handle)
        if isinstance(data, dict):
            entries = len(data)
    except (OSError, ValueError):
        entries = 0  # missing/corrupt cache: it rebuilds on demand
    print(f"Fingerprint cache: {cache} ({entries} entr{'y' if entries == 1 else 'ies'})")
    print(
        "AcoustID API key: "
        + ("set (saved in settings)" if fingerprints.acoustid_api_key() else "not set")
    )
    return 0


def cmd_jobs(args) -> int:
    """List the saved jobs."""
    names = jobs.list_jobs()
    if not names:
        print("No saved jobs.")
    for name in names:
        print(name)
    return 0


def cmd_job_save(args) -> int:
    """Save a project file as a named job.

    Pattern layers are state the GUI builds interactively (the
    filename-pattern dialog), so a CLI-saved job stores none — the
    note printed below says so out loud rather than letting the user
    discover a missing layer later.
    """
    project = Project.load(args.project_file)
    job = jobs.job_from_project(args.name, project, pattern_layers=())
    path = jobs.save_job(job)
    print(f"Saved job {job.name!r} to {path}")
    print(
        "Note: filename-pattern layers are GUI-side state, so this job "
        "stores none — it holds the project's MP3 paths, CSV layers "
        "and tag-name settings only."
    )
    return 0


def cmd_job_run(args) -> int:
    """Run a saved job; a dry run unless --apply is given.

    Rebuilds the job's project, scans, builds the ordinary preview,
    then applies the job's filename-pattern layers on top — exactly
    the steps the GUI's Run job button performs.
    """
    try:
        job = jobs.load_job(args.name)
    except FileNotFoundError as exc:
        raise SystemExit(str(exc)) from exc
    project = jobs.job_to_project(job)
    if args.log_folder:
        project.apply_log_folder = args.log_folder
    files = scan(project.mp3_paths, progress=_progress_printer("scan"))
    preview = build_preview(project, files=files)
    for layer in job.pattern_layers:
        values: dict[str, dict[str, str]] = {}
        for mp3 in files:
            try:
                captured = capture_for_file(
                    layer.get("pattern", ""), mp3.path,
                    root=layer.get("root") or None,
                    use_path=bool(layer.get("use_path")),
                )
            except ValueError as exc:
                raise SystemExit(
                    f"Job {job.name!r} has a bad pattern layer: {exc}"
                ) from exc
            if captured:
                values[mp3.path] = captured
        if values:
            add_value_layer(
                preview, files, values, "filename pattern",
                project.alternative_names,
            )
    _print_summary(preview)
    if not args.apply:
        print("Dry run — re-run with --apply to write these tags.")
        return 0
    result = apply_preview(
        preview,
        log_folder=project.apply_log_folder,
        progress=_progress_printer("write"),
    )
    _print_summary(preview, result)
    return 1 if result.errors else 0


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
    p.add_argument("--pattern", default="", help="filename/path pattern: report tags that disagree with the values the pattern captures from each file's path (read-only; replaces the duplicates/variants report)")
    p.add_argument("--root", default="", help="root folder for --pattern when it matches against paths")
    p.add_argument("--filename-only", action="store_true", help="with --pattern: match the pattern against file names only, not full paths")
    p.add_argument("--completeness", action="store_true", help="also print the per-album tag completeness section")
    p.add_argument("--same-recordings", action="store_true", help="also group files that are the same recording by audio fingerprint (needs fpcalc)")
    p.add_argument("--unify-from", default="", metavar="PATH", help="with --same-recordings: preview copying this file's tags to the other members of its same-recording group (the file must belong to exactly one group)")
    p.add_argument("--apply", action="store_true", help="with --unify-from: actually write (default is a dry run)")
    p.add_argument("--log-folder", default="", help="with --unify-from --apply: folder for the change log + undo snapshot")
    p.add_argument("--out", default="", help="also write the report to this file (.csv path = CSV format, otherwise text; with --unify-from it exports the preview CSV instead)")
    p.set_defaults(func=cmd_report)

    p = sub.add_parser("sync-tags", help="copy tags from a source library onto its twin library")
    p.add_argument("--source", required=True, help="folder of the library whose tags win")
    p.add_argument("--target", required=True, help="folder of the library whose tags are updated")
    p.add_argument("--tags", default="", help='comma-separated tags to copy (default: every text tag found on the paired source files)')
    p.add_argument("--no-cover", action="store_true", help="do not copy cover art")
    p.add_argument("--fingerprint-pairing", action="store_true", help="also pair leftover files by audio fingerprint (needs fpcalc)")
    p.add_argument("--log-folder", default="", help="folder for the change log + undo snapshot (extracted cover images are stored here too)")
    p.add_argument("--out", default="", help="also export the preview to this CSV")
    p.add_argument("--apply", action="store_true", help="actually write (default is a dry run)")
    p.set_defaults(func=cmd_sync_tags)

    p = sub.add_parser("acoustid", help="fill EMPTY tags from AcoustID (opt-in, online, needs your own API key)")
    p.add_argument("--folder", action="append", help="folder to scan recursively")
    p.add_argument("--file", action="append", help="a single MP3 file")
    p.add_argument("--key", default="", help="your AcoustID API key (default: the key saved in settings)")
    p.add_argument("--log-folder", default="", help="folder for the change log + undo snapshot")
    p.add_argument("--out", default="", help="also export the preview to this CSV")
    p.add_argument("--apply", action="store_true", help="actually write (default is a dry run)")
    p.set_defaults(func=cmd_acoustid)

    p = sub.add_parser("fingerprint-status", help="show whether fpcalc is available and the fingerprint cache state")
    p.set_defaults(func=cmd_fingerprint_status)

    p = sub.add_parser("jobs", help="list the saved jobs")
    p.set_defaults(func=cmd_jobs)

    p = sub.add_parser("job-save", help="save a project file as a named job (pattern layers are GUI-side state and are not stored)")
    p.add_argument("name", help="the job's name")
    p.add_argument("project_file", help="project file (.mp3p.json) to save as the job")
    p.set_defaults(func=cmd_job_save)

    p = sub.add_parser("job-run", help="run a saved job")
    p.add_argument("name", help="the job's name (or a path to a job JSON file)")
    p.add_argument("--apply", action="store_true", help="actually write (default is a dry run)")
    p.add_argument("--log-folder", default="", help="folder for the change log + undo snapshot")
    p.set_defaults(func=cmd_job_run)

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
