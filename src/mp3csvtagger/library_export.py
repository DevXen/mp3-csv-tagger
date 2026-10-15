"""Export a scanned MP3 library to CSV data.

This is the inverse of the tagging flow: instead of reading a CSV to
change files, it turns the files found by
:mod:`mp3csvtagger.mp3files` into a CSV — one row per file — that can
be opened in a spreadsheet, edited, and (after removing or keeping
the pseudo-columns as needed) fed back in as a tagging CSV.

Every export starts with three *pseudo-columns* that describe the
file itself rather than a stored tag:

* ``FileName`` — the file's base name, e.g. ``"01 Song.mp3"``.
* ``FilePath`` — the full path exactly as stored on the
  :class:`~mp3csvtagger.mp3files.Mp3File`.
* ``Folder`` — the containing folder path (``os.path.dirname`` of
  the full path).

After the pseudo-columns come the real tag names: the union of tag
names across all files, in first-appearance order while scanning the
files sorted by path — so the column order is deterministic for a
given library and does not depend on scan completion order.

Exports can also *append*: :func:`append_library_csv` merges a fresh
scan into an existing export CSV instead of replacing it, so a
library CSV can be built up folder by folder (see that function's
docstring for the merge rules).
"""

from __future__ import annotations

import os
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

from .csvfiles import CsvError, CsvFile, write_csv
from .mp3files import Mp3File

#: Pseudo-columns that describe the file itself, always exported first.
PSEUDO_COLUMNS: tuple[str, str, str] = ("FileName", "FilePath", "Folder")


def pseudo_value(mp3file: Mp3File, name: str) -> str:
    """Return the pseudo-column value *name* for *mp3file*.

    Args:
        mp3file: The file to describe.
        name: One of :data:`PSEUDO_COLUMNS` — ``"FileName"`` (base
            name), ``"FilePath"`` (full path) or ``"Folder"``
            (containing folder path).

    Returns:
        The requested value as a string.

    Raises:
        ValueError: If *name* is not a known pseudo-column.
    """
    if name == "FileName":
        return mp3file.filename
    if name == "FilePath":
        return mp3file.path
    if name == "Folder":
        return os.path.dirname(mp3file.path)
    raise ValueError(
        f"Unknown pseudo-column: {name!r}. Expected one of: "
        + ", ".join(PSEUDO_COLUMNS)
        + "."
    )


def _sorted_files(files: Iterable[Mp3File]) -> list[Mp3File]:
    """Return *files* as a list sorted by path (deterministic order).

    Args:
        files: The files to sort.

    Returns:
        A new list containing the same files, sorted by ``path``.
    """
    return sorted(files, key=lambda mp3file: mp3file.path)


def export_columns(files: Iterable[Mp3File]) -> list[str]:
    """Return the column names for exporting *files*.

    The pseudo-columns (:data:`PSEUDO_COLUMNS`) come first, followed
    by the union of tag names across all files in first-appearance
    order, scanning the files sorted by path.

    Args:
        files: The scanned files to export.

    Returns:
        The ordered column names.  For an empty library this is just
        the pseudo-columns.
    """
    columns: list[str] = list(PSEUDO_COLUMNS)
    seen: set[str] = set(columns)
    for mp3file in _sorted_files(files):
        for tag_name in mp3file.tags:
            if tag_name not in seen:
                seen.add(tag_name)
                columns.append(tag_name)
    return columns


def export_rows(files: Iterable[Mp3File]) -> list[dict[str, str]]:
    """Return one row ``dict`` per file, aligned with :func:`export_columns`.

    Rows are ordered by file path (the same deterministic order used
    by :func:`export_columns`).  Every row has exactly the keys of
    :func:`export_columns` for the same *files*; a tag a file does
    not have is exported as ``""``.

    Args:
        files: The scanned files to export.

    Returns:
        A list of ``{column: value}`` dicts, one per file.
    """
    file_list = _sorted_files(files)
    columns = export_columns(file_list)
    rows: list[dict[str, str]] = []
    for mp3file in file_list:
        row: dict[str, str] = {}
        for column in columns:
            if column in PSEUDO_COLUMNS:
                row[column] = pseudo_value(mp3file, column)
            else:
                row[column] = mp3file.tags.get(column, "")
        rows.append(row)
    return rows


def write_library_csv(
    files: Iterable[Mp3File], out_path: str | Path
) -> list[str]:
    """Write *files* to *out_path* as a CSV and return the columns used.

    The file is written with
    :func:`mp3csvtagger.csvfiles.write_csv`: the first row is the
    header from :func:`export_columns` and each following row is one
    file, in path order, with values in column order.

    Args:
        files: The scanned files to export.
        out_path: Destination CSV path.

    Returns:
        The column list that was written as the header.
    """
    file_list = list(files)
    columns = export_columns(file_list)
    rows = export_rows(file_list)
    sequences = [[row[column] for column in columns] for row in rows]
    write_csv(str(out_path), columns, sequences)
    return columns


@dataclass
class AppendSummary:
    """Outcome of one :func:`append_library_csv` merge.

    Attributes:
        files_scanned: How many files the new scan covered.
        rows_added: Scan files that had no row yet; their rows were
            appended at the end of the CSV.
        rows_updated: Existing rows whose file was in the scan; the
            scan's columns were refreshed in place (position kept).
        rows_kept: Existing rows left completely untouched (their
            file was not in this scan).
        columns_added: Tag columns the scan introduced that the CSV
            did not have; they were appended at the end of the
            header, blank for all pre-existing rows.
        key_column: The pseudo-column rows were matched on —
            ``"FilePath"`` normally, ``"FileName"`` as a fallback.
        warning: A human-readable caution about the merge (set when
            the fallback key was used), else ``None``.
    """

    files_scanned: int = 0
    rows_added: int = 0
    rows_updated: int = 0
    rows_kept: int = 0
    columns_added: list[str] = field(default_factory=list)
    key_column: str = "FilePath"
    warning: str | None = None


def append_library_csv(
    files: Iterable[Mp3File], out_path: str | Path
) -> AppendSummary:
    """Merge a fresh scan into the existing export CSV at *out_path*.

    This is how a library CSV gets built up folder by folder: export
    one folder, then append scans of other folders into the same
    file instead of juggling one CSV per folder.

    Merge rules:

    * Columns: the existing header order is preserved. Tag columns
      the scan produces that the CSV lacks are appended at the end
      (blank for rows that were already there).
    * Rows are keyed by the ``FilePath`` pseudo-column. An existing
      row whose file is in the scan is updated **in place** — same
      position, fresh values — but only for the columns this scan
      produces: a column the scan does not produce (say the CSV has
      a hand-written ``Comment`` column the scanned files don't use)
      is never erased by the merge. Existing rows whose files are
      not in the scan keep their rows, untouched, in place.
    * Scan files with no existing row are appended at the end, in
      the scan's path order.
    * If the existing CSV has no ``FilePath`` column (e.g. it was
      edited down in a spreadsheet), rows fall back to keying on
      ``FileName`` and the summary's ``warning`` says so — file names
      are weaker keys than paths, so two different files that share
      a name would collide.

    Args:
        files: The newly scanned files to merge in.
        out_path: The existing CSV to merge into. It is rewritten in
            place with the merged result.

    Returns:
        An :class:`AppendSummary` describing what the merge did.

    Raises:
        FileNotFoundError: If *out_path* does not exist — appending
            only makes sense into a file that is already there.
        CsvError: If the existing file has no header row, or has
            neither a ``FilePath`` nor a ``FileName`` column to key
            rows on.
    """
    path = Path(out_path)
    if not path.exists():
        raise FileNotFoundError(
            f"Cannot append: {out_path} does not exist. "
            "Export a new CSV first, then append further folders to it."
        )
    csv_file = CsvFile(str(path))
    headings = csv_file.headings()
    if not headings:
        raise CsvError(f"Cannot append: {out_path} has no header row.")

    summary = AppendSummary()
    if "FilePath" in headings:
        summary.key_column = "FilePath"
    elif "FileName" in headings:
        summary.key_column = "FileName"
        summary.warning = (
            f"{path.name} has no FilePath column, so rows were matched "
            "by FileName only. Different files that share a name would "
            "be treated as the same file — re-export with FilePath "
            "when you can."
        )
    else:
        raise CsvError(
            f"Cannot append: {out_path} has neither a FilePath nor a "
            "FileName column to match rows on."
        )
    key_column = summary.key_column

    file_list = list(files)
    summary.files_scanned = len(file_list)
    scan_columns = export_columns(file_list)
    scan_rows = export_rows(file_list)

    # Columns the scan introduces go at the end of the existing order.
    merged_columns = list(headings)
    for column in scan_columns:
        if column not in merged_columns:
            merged_columns.append(column)
            summary.columns_added.append(column)

    # Index the scan by its key value. A scan should not contain the
    # same file twice; if it somehow does, the first row wins so the
    # merge stays deterministic.
    scan_by_key: dict[str, dict[str, str]] = {}
    for row in scan_rows:
        scan_by_key.setdefault(row[key_column], row)

    merged_rows: list[dict[str, str]] = []
    for _index, values in csv_file.rows():
        existing = dict(zip(headings, values))
        key = existing.get(key_column, "")
        fresh = scan_by_key.pop(key, None) if key else None
        if fresh is None:
            summary.rows_kept += 1
            merged_rows.append(existing)
            continue
        # Update in place: only the columns this scan produces are
        # refreshed; every other column keeps the value already in
        # the CSV (hand edits and columns from other folders survive).
        updated = dict(existing)
        for column in scan_columns:
            updated[column] = fresh[column]
        summary.rows_updated += 1
        merged_rows.append(updated)

    # Whatever is left in the scan is new to this CSV: append at the
    # end, in the scan's own (path-sorted) order. Each key is appended
    # once and then removed, so a duplicated scan entry cannot
    # produce a duplicated row.
    for row in scan_rows:
        if row[key_column] in scan_by_key:
            merged_rows.append(row)
            summary.rows_added += 1
            del scan_by_key[row[key_column]]

    sequences = [
        [row.get(column, "") for column in merged_columns] for row in merged_rows
    ]
    write_csv(str(path), merged_columns, sequences)
    return summary
