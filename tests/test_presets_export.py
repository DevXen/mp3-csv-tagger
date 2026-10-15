"""Tests for column-role presets and library CSV export.

Presets are exercised entirely inside a ``tmp_path`` presets
directory (via the ``MP3CSVTAGGER_PRESETS_DIR`` environment override),
so the tests never touch the real ``~/.mp3csvtagger`` folder.
Export tests use synthetic :class:`Mp3File` objects — no real MP3
files or tag reading are needed.
"""

from __future__ import annotations

import csv
import json
import os

import pytest

from mp3csvtagger import library_export, presets
from mp3csvtagger.library_export import (
    PSEUDO_COLUMNS,
    export_columns,
    export_rows,
    pseudo_value,
    write_library_csv,
)
from mp3csvtagger.mp3files import Mp3File
from mp3csvtagger.presets import Preset
from mp3csvtagger.project import CsvEntry, CsvTag, Role


@pytest.fixture()
def presets_home(tmp_path, monkeypatch):
    """Point the presets directory at a fresh ``tmp_path`` folder."""
    directory = tmp_path / "presets"
    monkeypatch.setenv(presets.PRESETS_DIR_ENV_VAR, str(directory))
    return directory


# ---------------------------------------------------------------------------
# Preset data class
# ---------------------------------------------------------------------------

def test_preset_to_dict_from_dict_round_trip():
    preset = Preset(
        name="Round trip",
        roles={"Title": int(Role.Write), "Genre": int(Role.Match), "Rating": 3},
    )
    data = preset.to_dict()
    # JSON-safe: role values are plain ints and the dict survives JSON.
    assert json.loads(json.dumps(data)) == data
    assert all(isinstance(value, int) for value in data["roles"].values())
    restored = Preset.from_dict(data)
    assert restored == preset
    assert restored.name == "Round trip"
    assert restored.roles == {"Title": 2, "Genre": 1, "Rating": 3}


def test_preset_from_dict_coerces_role_values_to_int():
    preset = Preset.from_dict({"name": "X", "roles": {"Title": "2"}})
    assert preset.roles == {"Title": 2}
    assert isinstance(preset.roles["Title"], int)


# ---------------------------------------------------------------------------
# presets_dir / builtins
# ---------------------------------------------------------------------------

def test_presets_dir_uses_env_override_and_is_created(presets_home):
    directory = presets.presets_dir()
    assert str(directory) == str(presets_home)
    assert directory.is_dir()


def test_builtin_presets_names_and_roles():
    builtins = presets.builtin_presets()
    names = [preset.name for preset in builtins]
    assert "Match artist, write genre" in names
    assert "Fix titles by filename anchor" in names

    by_name = {preset.name: preset for preset in builtins}
    assert by_name["Match artist, write genre"].roles == {
        "Lead Performer": 1,
        "Artist": 1,
        "Genre": 2,
    }
    assert by_name["Fix titles by filename anchor"].roles == {
        "FileName": 1,
        "Title": 2,
    }
    # The values really are the Role enum's values.
    assert by_name["Match artist, write genre"].roles["Genre"] == int(Role.Write)
    assert by_name["Fix titles by filename anchor"].roles["FileName"] == int(Role.Match)


# ---------------------------------------------------------------------------
# save / load / list
# ---------------------------------------------------------------------------

def test_save_and_load_preset_round_trip_via_tmp_path(presets_home):
    preset = Preset(name="My Custom Preset", roles={"Title": 2, "Artist": 1})
    written = presets.save_preset(preset)

    # Slugified file name: spaces -> '-', only safe characters kept.
    assert written.parent == presets.presets_dir()
    assert written.name == "My-Custom-Preset.json"
    assert written.is_file()
    assert json.loads(written.read_text(encoding="utf-8")) == preset.to_dict()

    # Loadable by name, by slug-file lookup, and by explicit path.
    assert presets.load_preset("My Custom Preset") == preset
    assert presets.load_preset(str(written)) == preset
    assert presets.load_preset(written) == preset

    # And discoverable in the listing, alongside the builtins.
    listed = {p.name: p for p in presets.list_presets()}
    assert listed["My Custom Preset"] == preset
    assert "Match artist, write genre" in listed
    assert "Fix titles by filename anchor" in listed


def test_save_preset_slugifies_unsafe_characters(presets_home):
    preset = Preset(name="Fix: titles / now!", roles={"Title": 2})
    written = presets.save_preset(preset)
    assert "/" not in written.name
    assert ":" not in written.name
    assert "!" not in written.name
    assert written.suffix == ".json"
    assert presets.load_preset("Fix: titles / now!") == preset


def test_list_presets_user_preset_replaces_builtin(presets_home):
    replacement = Preset(name="Match artist, write genre", roles={"Genre": 3})
    presets.save_preset(replacement)

    listed = presets.list_presets()
    names = [preset.name for preset in listed]
    # No duplicate: the user version replaced the builtin.
    assert names.count("Match artist, write genre") == 1
    by_name = {preset.name: preset for preset in listed}
    assert by_name["Match artist, write genre"].roles == {"Genre": 3}
    # Loading by name also returns the user (replacement) version.
    assert presets.load_preset("Match artist, write genre") == replacement


def test_load_preset_builtin_by_name(presets_home):
    preset = presets.load_preset("Match artist, write genre")
    assert preset.roles == {"Lead Performer": 1, "Artist": 1, "Genre": 2}


def test_load_preset_from_arbitrary_json_path(tmp_path):
    path = tmp_path / "elsewhere.json"
    path.write_text(
        json.dumps({"name": "Elsewhere", "roles": {"Title": 2}}),
        encoding="utf-8",
    )
    assert presets.load_preset(str(path)) == Preset(
        name="Elsewhere", roles={"Title": 2}
    )


def test_load_preset_missing_raises_file_not_found(presets_home):
    with pytest.raises(FileNotFoundError) as excinfo:
        presets.load_preset("No Such Preset Exists")
    message = str(excinfo.value)
    assert "No Such Preset Exists" in message
    # The message is helpful: it names what *is* available.
    assert "Match artist, write genre" in message


# ---------------------------------------------------------------------------
# apply_preset
# ---------------------------------------------------------------------------

def test_apply_preset_changes_roles_and_counts():
    entry = CsvEntry(
        path="layer.csv",
        tags=[
            CsvTag(name="Lead Performer", role=int(Role.Skip)),
            CsvTag(name="Genre", role=int(Role.Skip)),
            CsvTag(name="Title", role=int(Role.Skip)),
            CsvTag(name="Rating", role=int(Role.Write)),
        ],
    )
    preset = Preset(
        name="Match artist, write genre",
        roles={"Lead Performer": 1, "Artist": 1, "Genre": 2},
    )
    changed = presets.apply_preset(entry, preset)

    # Only columns named in the preset *and* present on the entry count:
    # "Artist" is in the preset but not on the entry, so it is ignored.
    assert changed == 2
    roles = {tag.name: tag.role for tag in entry.tags}
    assert roles == {
        "Lead Performer": int(Role.Match),
        "Genre": int(Role.Write),
        "Title": int(Role.Skip),   # not in preset: unchanged
        "Rating": int(Role.Write),  # not in preset: unchanged
    }


def test_apply_preset_with_no_matching_columns_returns_zero():
    entry = CsvEntry(
        path="layer.csv",
        tags=[CsvTag(name="Title", role=int(Role.Skip))],
    )
    preset = Preset(name="Other", roles={"Genre": 2})
    assert presets.apply_preset(entry, preset) == 0
    assert entry.tags[0].role == int(Role.Skip)


def test_apply_builtin_preset_to_entry():
    entry = CsvEntry(
        path="layer.csv",
        tags=[
            CsvTag(name="FileName", role=int(Role.Skip)),
            CsvTag(name="Title", role=int(Role.Skip)),
        ],
    )
    builtin = {p.name: p for p in presets.builtin_presets()}[
        "Fix titles by filename anchor"
    ]
    assert presets.apply_preset(entry, builtin) == 2
    assert entry.tags[0].role == int(Role.Match)
    assert entry.tags[1].role == int(Role.Write)


# ---------------------------------------------------------------------------
# Library export
# ---------------------------------------------------------------------------

def make_files():
    """Two synthetic files with different (overlapping) tag sets.

    Deliberately returned out of path order: export must sort by path,
    so ``a.mp3`` is scanned first and its tags appear first.
    """
    second = Mp3File(
        path=os.path.join("/music", "sub", "b.mp3"),
        tags={"Title": "Song B", "Genre": "Jazz", "Year": "2001"},
    )
    first = Mp3File(
        path=os.path.join("/music", "a.mp3"),
        tags={"Title": "Song A", "Artist": "Artist A", "Genre": "Rock"},
    )
    return [second, first]


def test_pseudo_columns_constant():
    assert PSEUDO_COLUMNS == ("FileName", "FilePath", "Folder")
    assert library_export.PSEUDO_COLUMNS == PSEUDO_COLUMNS


def test_pseudo_value():
    mp3file = Mp3File(path=os.path.join("/music", "sub", "b.mp3"), tags={})
    assert pseudo_value(mp3file, "FileName") == "b.mp3"
    assert pseudo_value(mp3file, "FilePath") == os.path.join("/music", "sub", "b.mp3")
    assert pseudo_value(mp3file, "Folder") == os.path.join("/music", "sub")
    with pytest.raises(ValueError):
        pseudo_value(mp3file, "NotAPseudoColumn")


def test_export_columns_union_in_first_appearance_order_sorted_by_path():
    columns = export_columns(make_files())
    # Pseudo columns first, then a.mp3's tags (Title, Artist, Genre)
    # in their order, then the only new tag from b.mp3 (Year).
    assert columns == [
        "FileName",
        "FilePath",
        "Folder",
        "Title",
        "Artist",
        "Genre",
        "Year",
    ]


def test_export_rows_values_pseudo_columns_and_missing_tags():
    files = make_files()
    columns = export_columns(files)
    rows = export_rows(files)

    assert len(rows) == 2
    assert all(list(row.keys()) == columns for row in rows)

    first, second = rows  # sorted by path: a.mp3 before sub/b.mp3
    assert first["FileName"] == "a.mp3"
    assert first["FilePath"] == os.path.join("/music", "a.mp3")
    assert first["Folder"] == "/music"
    assert first["Title"] == "Song A"
    assert first["Artist"] == "Artist A"
    assert first["Genre"] == "Rock"
    assert first["Year"] == ""  # missing tag -> empty string

    assert second["FileName"] == "b.mp3"
    assert second["FilePath"] == os.path.join("/music", "sub", "b.mp3")
    assert second["Folder"] == os.path.join("/music", "sub")
    assert second["Title"] == "Song B"
    assert second["Artist"] == ""  # missing tag -> empty string
    assert second["Genre"] == "Jazz"
    assert second["Year"] == "2001"


def test_export_empty_library_has_only_pseudo_columns():
    assert export_columns([]) == ["FileName", "FilePath", "Folder"]
    assert export_rows([]) == []


def test_write_library_csv_writes_header_and_rows(tmp_path):
    files = make_files()
    out_path = tmp_path / "library.csv"
    columns = write_library_csv(files, out_path)

    assert columns == export_columns(files)
    with open(out_path, newline="", encoding="utf-8") as handle:
        read = list(csv.reader(handle))
    assert read[0] == columns
    assert len(read) == 3  # header + two files
    # Row order follows the sorted paths, values follow column order.
    expected = [
        [row[column] for column in columns] for row in export_rows(files)
    ]
    assert read[1:] == expected
    assert read[1][columns.index("FileName")] == "a.mp3"
    assert read[2][columns.index("FileName")] == "b.mp3"
