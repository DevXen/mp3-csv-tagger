"""Tests for append (merge) library export — building one library
CSV up folder by folder.

The merge rules under test (see ``library_export.append_library_csv``):

* existing column order is preserved; new scan columns append last;
* rows are keyed by FilePath (FileName fallback, with a warning);
* a re-scanned file's row updates in place, never duplicates;
* rows for files outside the scan are kept untouched;
* a column the scan does not produce never loses its values.
"""

from __future__ import annotations

import csv
import os

import pytest

from mp3csvtagger.csvfiles import CsvError, write_csv
from mp3csvtagger.library_export import append_library_csv, write_library_csv
from mp3csvtagger.mp3files import Mp3File


def folder_a():
    """First folder: two files, Title/Artist/Genre."""
    return [
        Mp3File(
            path=os.path.join("/music", "a", "one.mp3"),
            tags={"Title": "One", "Artist": "Artist A", "Genre": "Rock"},
        ),
        Mp3File(
            path=os.path.join("/music", "a", "two.mp3"),
            tags={"Title": "Two", "Artist": "Artist A", "Genre": "Rock"},
        ),
    ]


def folder_b():
    """Second folder: two files, one introducing a Year column."""
    return [
        Mp3File(
            path=os.path.join("/music", "b", "three.mp3"),
            tags={"Title": "Three", "Artist": "Artist B", "Year": "1999"},
        ),
        Mp3File(
            path=os.path.join("/music", "b", "four.mp3"),
            tags={"Title": "Four", "Artist": "Artist B"},
        ),
    ]


def read_csv(path):
    with open(path, newline="", encoding="utf-8") as handle:
        rows = list(csv.reader(handle))
    return rows[0], rows[1:]


def test_append_second_folder_unions_rows_and_columns(tmp_path):
    out = tmp_path / "library.csv"
    write_library_csv(folder_a(), out)

    summary = append_library_csv(folder_b(), out)

    assert summary.files_scanned == 2
    assert summary.rows_added == 2
    assert summary.rows_updated == 0
    assert summary.rows_kept == 2
    assert summary.key_column == "FilePath"
    assert summary.warning is None
    assert summary.columns_added == ["Year"]

    header, rows = read_csv(out)
    # Existing column order preserved, Year appended at the end.
    assert header == [
        "FileName", "FilePath", "Folder", "Title", "Artist", "Genre", "Year",
    ]
    assert len(rows) == 4
    by_name = {row[0]: row for row in rows}
    # Folder A rows kept their position at the top and gained a blank
    # Year; folder B rows appended after them in path order
    # ("four.mp3" sorts before "three.mp3").
    assert [row[0] for row in rows] == ["one.mp3", "two.mp3", "four.mp3", "three.mp3"]
    assert by_name["one.mp3"][header.index("Year")] == ""
    # Folder B rows carry their values; missing tags are blank.
    assert by_name["three.mp3"][header.index("Year")] == "1999"
    assert by_name["three.mp3"][header.index("Genre")] == ""
    assert by_name["four.mp3"][header.index("Title")] == "Four"


def test_append_rescan_updates_rows_in_place_without_duplicates(tmp_path):
    out = tmp_path / "library.csv"
    write_library_csv(folder_a(), out)
    append_library_csv(folder_b(), out)

    changed = folder_a()
    changed[0].tags["Genre"] = "Metal"  # tag edited since the first export
    summary = append_library_csv(changed, out)

    assert summary.rows_updated == 2
    assert summary.rows_added == 0
    assert summary.rows_kept == 2  # folder B rows untouched

    header, rows = read_csv(out)
    assert len(rows) == 4  # no duplicates
    assert [row[0] for row in rows] == ["one.mp3", "two.mp3", "four.mp3", "three.mp3"]
    by_name = {row[0]: row for row in rows}
    assert by_name["one.mp3"][header.index("Genre")] == "Metal"
    assert by_name["three.mp3"][header.index("Title")] == "Three"


def test_append_preserves_unrelated_rows_and_columns(tmp_path):
    out = tmp_path / "library.csv"
    # A CSV with a hand-written Comment column and a row for a file
    # that is not part of any scan here.
    write_csv(
        str(out),
        ["FileName", "FilePath", "Folder", "Title", "Comment"],
        [
            ["one.mp3", os.path.join("/music", "a", "one.mp3"),
             os.path.join("/music", "a"), "One", "keep me"],
            ["other.mp3", os.path.join("/elsewhere", "other.mp3"),
             "/elsewhere", "Other", "untouched"],
        ],
    )

    summary = append_library_csv(folder_a(), out)

    assert summary.rows_updated == 1  # one.mp3 refreshed
    assert summary.rows_kept == 1     # other.mp3 left alone
    assert summary.rows_added == 1    # two.mp3 is new

    header, rows = read_csv(out)
    by_name = {row[0]: row for row in rows}
    # The scan does not produce a Comment column, so the value the
    # user already had survives the refresh of one.mp3's row.
    assert by_name["one.mp3"][header.index("Comment")] == "keep me"
    assert by_name["one.mp3"][header.index("Genre")] == "Rock"  # new column value
    # The unrelated row is byte-for-byte the same values.
    assert by_name["other.mp3"][header.index("Comment")] == "untouched"
    assert by_name["other.mp3"][header.index("Genre")] == ""


def test_append_falls_back_to_filename_key_with_warning(tmp_path):
    out = tmp_path / "library.csv"
    # Spreadsheet-trimmed CSV: FilePath column deleted by hand.
    write_csv(
        str(out),
        ["FileName", "Title", "Artist"],
        [["one.mp3", "One", "Artist A"], ["gone.mp3", "Gone", "Nobody"]],
    )

    summary = append_library_csv(folder_a(), out)

    assert summary.key_column == "FileName"
    assert summary.warning is not None and "FileName" in summary.warning
    assert summary.rows_updated == 1  # one.mp3 matched by name
    assert summary.rows_added == 1    # two.mp3 appended
    assert summary.rows_kept == 1     # gone.mp3 untouched

    header, rows = read_csv(out)
    assert [row[0] for row in rows] == ["one.mp3", "gone.mp3", "two.mp3"]
    by_name = {row[0]: row for row in rows}
    assert by_name["one.mp3"][header.index("Genre")] == "Rock"
    assert by_name["gone.mp3"][header.index("Title")] == "Gone"


def test_append_requires_existing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        append_library_csv(folder_a(), tmp_path / "missing.csv")


def test_append_rejects_headerless_and_keyless_files(tmp_path):
    empty = tmp_path / "empty.csv"
    empty.write_text("", encoding="utf-8")
    with pytest.raises(CsvError):
        append_library_csv(folder_a(), empty)

    keyless = tmp_path / "keyless.csv"
    write_csv(str(keyless), ["Title", "Artist"], [["One", "Artist A"]])
    with pytest.raises(CsvError):
        append_library_csv(folder_a(), keyless)
