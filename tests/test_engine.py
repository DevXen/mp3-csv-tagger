"""End-to-end tests for the tagging engine (scan -> preview -> apply).

They build real MP3 files (a minimal silent MPEG stream with an ID3 header)
and real CSVs in a temp folder, then check the tags on disk afterwards —
including the layered-CSV behaviour and the custom TXXX case from the
original program's own test files.
"""

from __future__ import annotations

import csv
import os
import sys

import pytest
from mutagen.id3 import ID3, TALB, TCON, TIT2, TPE1

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "examples"))
from make_sample_mp3s import SILENT_MP3  # noqa: E402

from mp3csvtagger.apply import apply_preview  # noqa: E402
from mp3csvtagger.matching import normalize  # noqa: E402
from mp3csvtagger.preview import build_preview  # noqa: E402
from mp3csvtagger.project import Project, Role  # noqa: E402
from mp3csvtagger.tags import frame_for_tag_name  # noqa: E402


def make_mp3(folder, name, *, title, artist, genre):
    path = os.path.join(folder, name)
    with open(path, "wb") as handle:
        handle.write(SILENT_MP3)
    audio = ID3()
    audio.add(TIT2(text=[title]))
    audio.add(TPE1(text=[artist]))
    audio.add(TALB(text=["Rage Against the Machine"]))
    audio.add(TCON(text=[genre]))
    audio.save(path)
    return path


def make_csv(folder, name, header, rows):
    path = os.path.join(folder, name)
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)
    return path


def set_roles(entry, **roles):
    for tag in entry.tags:
        if tag.name in roles:
            tag.role = roles[tag.name]


@pytest.fixture()
def library(tmp_path):
    folder = str(tmp_path)
    song = make_mp3(
        folder, "01 Township Rebellion.mp3",
        title="Township Rebellion",
        artist="Rage Against the Machine", genre="Rock",
    )
    other = make_mp3(
        folder, "02 Other Band.mp3",
        title="Something Else", artist="Another Band", genre="Jazz",
    )
    return folder, song, other


def test_normalize_matches_original_rule():
    assert normalize("Rage Against the Machine") == normalize("rage against the machine!")
    assert normalize("Don't Stop!") == normalize("dont stop")
    assert normalize(None) == ""


def test_frame_resolution():
    assert frame_for_tag_name("TIT2") == "TIT2"
    assert frame_for_tag_name("Title") == "TIT2"
    assert frame_for_tag_name("Lead Performer") == "TPE1"  # the original's mapping
    assert frame_for_tag_name("Artist") == "TPE1"
    assert frame_for_tag_name("Subgenre") == "TXXX"  # unknown -> custom tag


def test_preview_and_apply_with_layered_csvs(library, tmp_path):
    folder, song, other = library
    sample1 = make_csv(
        folder, "Sample1.csv",
        ["Lead Performer", "Genre", "Subgenre"],
        [["Rage Against the Machine", "Rap Metal", "Political Rap Metal"]],
    )
    sample2 = make_csv(
        folder, "Sample2.csv",
        ["Genre", "Rating"],
        [["Rap Metal", "5"]],
    )
    project = Project()
    project.add_mp3_path(folder)
    entry1 = project.add_csv_file(sample1)
    set_roles(entry1, **{"Lead Performer": Role.Match, "Genre": Role.Write,
                         "Subgenre": Role.Write})
    entry2 = project.add_csv_file(sample2)
    # Sample2 matches on the Genre that Sample1 *writes* (layering).
    set_roles(entry2, **{"Genre": Role.Match, "Rating": Role.Write})

    preview = build_preview(project)
    assert preview.files_scanned == 2
    assert preview.files_matched == 1  # only the Rage track matches
    row = preview.row_for_path(song)
    assert row is not None
    assert row.cells["Genre"].old_value == "Rock"
    assert row.cells["Genre"].value == "Rap Metal"
    assert row.cells["Rating"].value == "5"

    log_folder = str(tmp_path / "logs")
    result = apply_preview(preview, log_folder=log_folder)
    assert result.errors == []
    assert result.files_written == 1
    assert result.log_file and os.path.isfile(result.log_file)

    audio = ID3(song)
    assert str(audio["TCON"].text[0]) == "Rap Metal"
    assert str(audio["TXXX:Subgenre"].text[0]) == "Political Rap Metal"
    assert str(audio["TXXX:Rating"].text[0]) == "5"
    # The unmatched file was not touched.
    assert str(ID3(other)["TCON"].text[0]) == "Jazz"

    # Change log has the original's columns and the old -> new values.
    with open(result.log_file, encoding="utf-8") as handle:
        rows = list(csv.reader(handle))
    assert rows[0] == ["Timestamp", "File", "Tag Name", "ID3 Frame",
                       "Original/Old Value", "New Value"]
    genre_rows = [r for r in rows[1:] if r[2] == "Genre"]
    assert genre_rows and genre_rows[0][4] == "Rock" and genre_rows[0][5] == "Rap Metal"


def test_multiple_candidates_last_layer_wins_and_can_be_reselected(library):
    folder, song, _other = library
    first = make_csv(folder, "a.csv", ["Lead Performer", "Genre"],
                     [["Rage Against the Machine", "Metal"]])
    second = make_csv(folder, "b.csv", ["Lead Performer", "Genre"],
                      [["Rage Against the Machine", "Rap Metal"]])
    project = Project()
    project.add_mp3_path(folder)
    for path in (first, second):
        entry = project.add_csv_file(path)
        set_roles(entry, **{"Lead Performer": Role.Match, "Genre": Role.Write})
    preview = build_preview(project)
    cell = preview.row_for_path(song).cells["Genre"]
    assert cell.has_multiple
    assert cell.value == "Rap Metal"  # later layer selected by default
    cell.selected = 0
    assert cell.value == "Metal"  # ...but the user can pick the other value


def test_file_without_id3_header_is_scanned_not_fatal(tmp_path):
    folder = str(tmp_path)
    bare = os.path.join(folder, "bare.mp3")
    with open(bare, "wb") as handle:
        handle.write(SILENT_MP3)  # no ID3 header at all
    csv_path = make_csv(folder, "x.csv", ["Title"], [["New Title"]])
    project = Project()
    project.add_mp3_path(folder)
    entry = project.add_csv_file(csv_path)
    set_roles(entry, **{"Title": Role.Write})
    preview = build_preview(project)  # original program crashed on this file
    assert preview.files_matched == 1
    result = apply_preview(preview, log_folder=None)
    assert result.errors == []
    assert str(ID3(bare)["TIT2"].text[0]) == "New Title"


def test_project_round_trip(tmp_path):
    project = Project()
    project.add_mp3_path("/music")
    path = str(tmp_path / "p.mp3p.json")
    project.save(path)
    loaded = Project.load(path)
    assert loaded.mp3_paths == ["/music"]
    assert loaded.alternative_names["TPE1"] == "Lead Performer"
