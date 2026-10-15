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
"""

from __future__ import annotations

import os
from collections.abc import Iterable
from pathlib import Path

from .csvfiles import write_csv
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
