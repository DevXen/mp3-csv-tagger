"""Applying a preview: writing the selected tags back into the MP3 files.

For each changed file this opens the MP3 **once**, replaces each selected
tag, and saves once.

Two records are written to the log folder (default ``~/mp3tagging``):

* a change log, ``mp3tag_YYYYMMDD_HHMMSS.log.csv`` with the columns
  ``Timestamp, File, Tag Name, ID3 Frame, Original/Old Value, New Value,
  Source`` — the Source is the selected candidate's source name, so the
  log shows which CSV (or "manual edit", or a virtual layer such as
  "tag sync") each written value came from;
* an undo snapshot, ``mp3tag_YYYYMMDD_HHMMSS.undo``, holding the *tags*
  each changed file had before the run — never copies of the audio, so
  even a huge run leaves a small file. See :mod:`.undo`.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field

from mutagen.id3 import ID3

from . import coverart, undo
from .csvfiles import write_csv
from .preview import Preview
from .tags import create_frame

LOG_HEADERS = [
    "Timestamp",
    "File",
    "Tag Name",
    "ID3 Frame",
    "Original/Old Value",
    "New Value",
    # Trailing on purpose: the first six columns keep the positions
    # existing log readers expect, and the source name is extra detail.
    "Source",
]


@dataclass
class ApplyResult:
    """Outcome of an apply run (counts, the files written, any errors)."""

    files_written: int = 0
    tags_written: int = 0
    files_unchanged: int = 0
    errors: list[str] = field(default_factory=list)
    log_file: str | None = None
    undo_file: str | None = None
    messages: list[str] = field(default_factory=list)


def _display_value(cell) -> str:
    """How a cell's value appears in logs/exports (cover art is a path)."""
    if cell.frame == "APIC":
        return coverart.cover_display(cell.value)
    return cell.value


def apply_preview(
    preview: Preview,
    *,
    log_folder: str | None = None,
    write_unchanged: bool = False,
    progress=None,
) -> ApplyResult:
    """Write the preview's selected values to disk.

    ``progress(done, total, path)`` is called per file, if given. Unchanged
    tags are skipped unless *write_unchanged* is set. When *log_folder* is
    given, a change log and an undo snapshot are written there; the undo
    snapshot is the only supported way to reverse a run, so callers that
    want undo must pass a log folder.
    """
    result = ApplyResult()
    log_rows: list[list[str]] = []
    undo_entries: list[dict] = []
    stamp = time.strftime("%Y%m%d_%H%M%S")

    rows = [row for row in preview.rows if row.cells]
    for done, row in enumerate(rows, start=1):
        if progress is not None:
            progress(done, len(rows), row.path)
        changes = [
            cell
            for cell in row.cells.values()
            if cell.candidates and (write_unchanged or cell.changed)
        ]
        if not changes:
            result.files_unchanged += 1
            continue
        try:
            # Snapshot BEFORE touching the file. The snapshot stores tag
            # frames only (plus the old cover if this run changes it) —
            # the audio itself is never copied.
            include_apic = any(cell.frame == "APIC" for cell in changes)
            entry = undo.make_entry(row.path, include_apic=include_apic)
            try:
                audio = ID3(row.path)
            except Exception:
                audio = ID3()  # no header yet: start a new one
            for cell in changes:
                if cell.frame == "APIC":
                    _apply_cover_cell(audio, cell)
                else:
                    # Remove existing frames for this tag first so a
                    # changed custom description can't leave a duplicate.
                    if cell.frame == "TXXX":
                        audio.delall(f"TXXX:{cell.tag_name}")
                    else:
                        audio.delall(cell.frame)
                    audio.add(create_frame(cell.frame, cell.tag_name, cell.value))
                # The Source column is the selected candidate's source
                # name: the CSV file name for CSV values, "manual edit"
                # for hand-typed values, the virtual layer's name
                # otherwise. ``changes`` only holds cells that have
                # candidates, but stay defensive about the index anyway.
                selected = (
                    cell.candidates[cell.selected] if cell.candidates else None
                )
                log_rows.append(
                    [
                        time.strftime("%Y/%m/%d %H:%M:%S"),
                        row.path,
                        cell.tag_name,
                        cell.frame,
                        cell.old_value,
                        _display_value(cell),
                        selected.csv_name if selected else "",
                    ]
                )
                result.tags_written += 1
            audio.save(row.path)
            # The undo guard compares against the file as THIS run left
            # it: refresh the entry's stat now that the save is done, so
            # undo can tell "untouched since our run" from "changed".
            entry["size"] = int(os.path.getsize(row.path))
            entry["mtime"] = int(os.path.getmtime(row.path))
            entry["had_no_header"] = entry.get("had_no_header", False)
            undo_entries.append(entry)
            result.files_written += 1
            result.messages.append(f"Applying tags to {row.path}")
        except Exception as exc:  # keep going: one bad file shouldn't stop a run
            result.errors.append(f"{row.path}: {exc}")
            result.messages.append(f"ERROR writing {row.path}: {exc}")

    if log_folder is not None:
        os.makedirs(log_folder, exist_ok=True)
        log_name = f"mp3tag_{stamp}.log.csv"
        result.log_file = os.path.join(log_folder, log_name)
        write_csv(result.log_file, LOG_HEADERS, log_rows)
        result.messages.append(
            f"Completed. Log of old and new values: {result.log_file}"
        )
        if undo_entries:
            result.undo_file = os.path.join(log_folder, f"mp3tag_{stamp}.undo")
            undo.write_undo_file(result.undo_file, undo_entries)
            result.messages.append(f"Undo snapshot: {result.undo_file}")
    return result


def _apply_cover_cell(audio: ID3, cell) -> None:
    """Apply one Cover Art cell: embed the image, or remove art if blank.

    The cell value is an image path, resolved relative to the folder of
    the CSV the value came from (recorded on the selected candidate).
    A blank value removes existing cover art — that is deliberate, is
    shown in the preview as "[remove cover art]", and is undoable
    because apply snapshots the old APIC frame for cover changes.
    """
    audio.delall("APIC")
    if not cell.value.strip():
        return  # removal only
    selected = cell.candidates[cell.selected]
    csv_dir = os.path.dirname(selected.csv_path) if selected.csv_path else None
    image_path = coverart.resolve_image_path(cell.value, csv_dir)
    audio.add(coverart.make_cover_frame(image_path))


def write_preview_csv(preview: Preview, path: str) -> None:
    """Export a preview as CSV (file, tag, old value, new value, changed…)."""
    header = [
        "File",
        "Tag Name",
        "ID3 Frame",
        "Old Value",
        "New Value",
        "Changed",
        "Candidates",
        "Source CSV",
        "Source Row",
    ]
    rows = []
    for row in preview.rows:
        for cell in row.cells.values():
            selected = cell.candidates[cell.selected] if cell.candidates else None
            rows.append(
                [
                    row.path,
                    cell.tag_name,
                    cell.frame,
                    cell.old_value,
                    _display_value(cell),
                    "yes" if cell.changed else "no",
                    len(cell.candidates),
                    selected.csv_name if selected else "",
                    selected.csv_row_index if selected else "",
                ]
            )
    write_csv(path, header, rows)
