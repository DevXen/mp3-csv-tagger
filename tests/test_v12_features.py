"""Integration tests for the v1.2.0 features wired into preview/apply.

The standalone modules (undo, filename_tags, library_report, presets,
library_export, musicbrainz, coverart) have their own suites; these tests
cover the integration: pseudo-columns in matching, Cover Art cells,
apply -> undo round-trips through :func:`apply_preview`, virtual layers
(filename captures, spelling unification) and export -> re-import.
"""

from __future__ import annotations

import csv
import os
import sys

import pytest
from mutagen.id3 import ID3, APIC, TCON, TIT2, TPE1

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "examples"))
from make_sample_mp3s import SILENT_MP3  # noqa: E402

from mp3csvtagger import undo  # noqa: E402
from mp3csvtagger.apply import apply_preview  # noqa: E402
from mp3csvtagger.filename_tags import capture_for_file  # noqa: E402
from mp3csvtagger.library_export import write_library_csv  # noqa: E402
from mp3csvtagger.library_report import variant_groups  # noqa: E402
from mp3csvtagger.mp3files import scan  # noqa: E402
from mp3csvtagger.preview import add_value_layer, build_preview, empty_preview  # noqa: E402
from mp3csvtagger.project import Project, Role  # noqa: E402

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + bytes(64)


def make_mp3(folder, name, *, title="Title", artist="Artist", genre="Rock",
             cover: bytes | None = None):
    """A small tagged MP3 on disk (optionally with cover art)."""
    path = os.path.join(folder, name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as handle:
        handle.write(SILENT_MP3)
    audio = ID3()
    audio.add(TIT2(text=[title]))
    audio.add(TPE1(text=[artist]))
    audio.add(TCON(text=[genre]))
    if cover:
        audio.add(APIC(encoding=3, mime="image/png", type=3, desc="",
                       data=cover))
    audio.save(path)
    return path


def make_csv(folder, name, header, rows):
    """Write a CSV file and return its path."""
    path = os.path.join(folder, name)
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)
    return path


def project_with(folder, csv_path, roles):
    """A Project over *folder* with one CSV entry and the given roles."""
    project = Project()
    project.add_mp3_path(folder)
    entry = project.add_csv_file(csv_path)
    for tag in entry.tags:
        if tag.name in roles:
            tag.role = roles[tag.name]
    return project


def test_pseudo_column_matches_and_writes_rejected(tmp_path):
    folder = str(tmp_path)
    song = make_mp3(folder, "01 Township Rebellion.mp3",
                    title="Township Rebellion", genre="Rock")
    make_mp3(folder, "02 Other.mp3", title="Other", genre="Jazz")
    csv_path = make_csv(folder, "fix.csv", ["FileName", "Genre"],
                        [["01 Township Rebellion.mp3", "Rap Metal"]])
    project = project_with(folder, csv_path,
                           {"FileName": Role.Match, "Genre": Role.Write})
    preview = build_preview(project)
    assert preview.files_matched == 1
    assert preview.row_for_path(song).cells["Genre"].value == "Rap Metal"

    bad = project_with(folder, csv_path,
                       {"FileName": Role.Write, "Genre": Role.Write})
    with pytest.raises(ValueError, match="never to Write"):
        build_preview(bad)


def test_cover_art_embed_remove_and_undo(tmp_path):
    folder = str(tmp_path)
    song = make_mp3(folder, "song.mp3", title="Song")
    image = os.path.join(folder, "cover.png")
    with open(image, "wb") as handle:
        handle.write(PNG_BYTES)
    csv_path = make_csv(folder, "art.csv", ["Title", "Cover Art"],
                        [["Song", "cover.png"]])
    project = project_with(folder, csv_path,
                           {"Title": Role.Match, "Cover Art": Role.Write})
    log_folder = str(tmp_path / "logs")
    preview = build_preview(project)
    cell = preview.row_for_path(song).cells["Cover Art"]
    assert cell.old_value == "" and cell.changed
    result = apply_preview(preview, log_folder=log_folder)
    assert result.errors == []
    assert ID3(song).getall("APIC")[0].data == PNG_BYTES
    assert result.undo_file and os.path.isfile(result.undo_file)

    # Undo removes the cover this run embedded.
    undo_result = undo.undo_run(result.undo_file)
    assert undo_result.restored == 1, undo_result.messages
    assert ID3(song).getall("APIC") == []

    # Now give it a cover and remove it via a blank cell; undo restores it.
    audio = ID3(song)
    audio.add(APIC(encoding=3, mime="image/png", type=3, desc="", data=PNG_BYTES))
    audio.save(song)
    csv2 = make_csv(folder, "art2.csv", ["Title", "Cover Art"], [["Song", ""]])
    project2 = project_with(folder, csv2,
                            {"Title": Role.Match, "Cover Art": Role.Write})
    result2 = apply_preview(build_preview(project2), log_folder=log_folder)
    assert result2.errors == []
    assert ID3(song).getall("APIC") == []
    undo.undo_run(result2.undo_file)
    assert ID3(song).getall("APIC")[0].data == PNG_BYTES


def test_apply_undo_roundtrip_and_modified_file_skipped(tmp_path):
    folder = str(tmp_path)
    song = make_mp3(folder, "a.mp3", title="Old Title", genre="Rock")
    csv_path = make_csv(folder, "t.csv", ["Lead Performer", "Genre", "Mood"],
                        [["Artist", "Metal", "Angry"]])
    project = project_with(
        folder, csv_path,
        {"Lead Performer": Role.Match, "Genre": Role.Write, "Mood": Role.Write},
    )
    log_folder = str(tmp_path / "logs")
    result = apply_preview(build_preview(project), log_folder=log_folder)
    assert result.errors == []
    audio = ID3(song)
    assert str(audio["TCON"].text[0]) == "Metal"
    assert str(audio["TXXX:Mood"].text[0]) == "Angry"

    # A file changed since the run is skipped by undo, not clobbered.
    stat = os.stat(song)
    os.utime(song, (stat.st_atime + 100, stat.st_mtime + 100))
    skipped = undo.undo_run(result.undo_file)
    assert skipped.restored == 0 and len(skipped.skipped) == 1
    assert str(ID3(song)["TCON"].text[0]) == "Metal"

    forced = undo.undo_run(result.undo_file, force=True)
    assert forced.restored == 1
    audio = ID3(song)
    assert str(audio["TCON"].text[0]) == "Rock"
    assert audio.getall("TXXX:Mood") == []


def test_tags_from_filename_virtual_layer(tmp_path):
    folder = str(tmp_path)
    song = make_mp3(folder, "Rage Against the Machine - Bombtrack.mp3",
                    title="Unknown", artist="Unknown")
    files = scan([folder])
    values = {}
    for mp3 in files:
        captured = capture_for_file(
            "{Lead Performer} - {Title}", mp3.path, use_path=False
        )
        if captured:
            values[mp3.path] = captured
    assert values[song]["Lead Performer"] == "Rage Against the Machine"
    preview = empty_preview(files)
    add_value_layer(preview, files, values, "filename pattern")
    result = apply_preview(preview, log_folder=str(tmp_path / "logs"))
    assert result.errors == []
    audio = ID3(song)
    assert str(audio["TIT2"].text[0]) == "Bombtrack"
    assert str(audio["TPE1"].text[0]) == "Rage Against the Machine"


def test_variant_unify_via_virtual_layer(tmp_path):
    folder = str(tmp_path)
    a = make_mp3(folder, "a.mp3", title="One", artist="beatles")
    b = make_mp3(folder, "b.mp3", title="Two", artist="Beatles")
    files = scan([folder])
    groups = variant_groups(files, "Lead Performer")
    assert len(groups) == 1
    canonical = "Beatles"
    values = {
        path: {"Lead Performer": canonical}
        for spelling, paths in groups[0]["spellings"].items()
        if spelling != canonical
        for path in paths
    }
    assert set(values) == {a}
    preview = empty_preview(files)
    add_value_layer(preview, files, values, "library report")
    result = apply_preview(preview, log_folder=str(tmp_path / "logs"))
    assert result.errors == []
    assert str(ID3(a)["TPE1"].text[0]) == "Beatles"
    assert str(ID3(b)["TPE1"].text[0]) == "Beatles"


def test_export_then_reimport_by_filename(tmp_path):
    folder = str(tmp_path)
    song = make_mp3(folder, "x.mp3", title="X", genre="Rock")
    files = scan([folder])
    exported = os.path.join(folder, "library.csv")
    columns = write_library_csv(files, exported)
    assert columns[:3] == ["FileName", "FilePath", "Folder"]
    # Edit the export: change the genre, then feed it back as a layer.
    with open(exported, encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    rows[0]["Genre"] = "Metal"
    edited = os.path.join(folder, "edited.csv")
    with open(edited, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    project = project_with(str(tmp_path), edited,
                           {"FileName": Role.Match, "Genre": Role.Write})
    preview = build_preview(project)
    assert preview.row_for_path(song).cells["Genre"].value == "Metal"


def test_lyrics_column_writes_uslt(tmp_path):
    folder = str(tmp_path)
    song = make_mp3(folder, "l.mp3", title="Song")
    csv_path = make_csv(folder, "lyr.csv", ["Title", "Lyrics"],
                        [["Song", "La la la"]])
    project = project_with(folder, csv_path,
                           {"Title": Role.Match, "Lyrics": Role.Write})
    result = apply_preview(build_preview(project),
                           log_folder=str(tmp_path / "logs"))
    assert result.errors == []
    from mp3csvtagger.mp3files import read_tags
    assert read_tags(song).tags["USLT"] == "La la la"
