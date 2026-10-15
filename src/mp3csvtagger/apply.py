"""Applying a preview: writing the selected tags back into the MP3 files.

For each changed file this opens the MP3 **once**, replaces each selected
tag, and saves once — the original opened and saved through a chain of
callbacks and wrote a database row per tag along the way.

A change log is always written (unless disabled), in the original's format:
``mp3tag_YYYYMMDD_HHMMSS.log.csv`` with the columns
``Timestamp, File, Tag Name, ID3 Frame, Original/Old Value, New Value``.
It lands in the project's log/backup folder (default ``~/mp3tagging``) and is
your undo reference: it records exactly what every file used to say.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field

from mutagen.id3 import ID3

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
]


@dataclass
class ApplyResult:
    files_written: int = 0
    tags_written: int = 0
    files_unchanged: int = 0
    errors: list[str] = field(default_factory=list)
    log_file: str | None = None
    messages: list[str] = field(default_factory=list)


def apply_preview(
    preview: Preview,
    *,
    log_folder: str | None = None,
    write_unchanged: bool = False,
    progress=None,
) -> ApplyResult:
    """Write the preview's selected values to disk.

    ``progress(done, total, path)`` is called per file, if given. Unchanged
    tags are skipped unless *write_unchanged* is set.
    """
    result = ApplyResult()
    log_rows: list[list[str]] = []

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
            try:
                audio = ID3(row.path)
            except Exception:
                audio = ID3()  # no header yet: start a new one
            for cell in changes:
                # Remove existing frames for this tag first so a rename or a
                # changed custom description can't leave a stale duplicate.
                if cell.frame == "TXXX":
                    audio.delall(f"TXXX:{cell.tag_name}")
                else:
                    audio.delall(cell.frame)
                audio.add(create_frame(cell.frame, cell.tag_name, cell.value))
                log_rows.append(
                    [
                        time.strftime("%Y/%m/%d %H:%M:%S"),
                        row.path,
                        cell.tag_name,
                        cell.frame,
                        cell.old_value,
                        cell.value,
                    ]
                )
                result.tags_written += 1
            audio.save(row.path)
            result.files_written += 1
            result.messages.append(f"Applying tags to {row.path}")
        except Exception as exc:  # keep going: one bad file shouldn't stop a run
            result.errors.append(f"{row.path}: {exc}")
            result.messages.append(f"ERROR writing {row.path}: {exc}")

    if log_folder is not None:
        os.makedirs(log_folder, exist_ok=True)
        log_name = "mp3tag_" + time.strftime("%Y%m%d_%H%M%S") + ".log.csv"
        result.log_file = os.path.join(log_folder, log_name)
        write_csv(result.log_file, LOG_HEADERS, log_rows)
        result.messages.append(
            f"Completed. Log of old and new values: {result.log_file}"
        )
    return result


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
                    cell.value,
                    "yes" if cell.changed else "no",
                    len(cell.candidates),
                    selected.csv_name if selected else "",
                    selected.csv_row_index if selected else "",
                ]
            )
    write_csv(path, header, rows)
