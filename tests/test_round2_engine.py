"""Tests for the round-2 engine additions.

Covered here, module by module:

* R1 manual preview edits (:mod:`mp3csvtagger.preview` +
  :mod:`mp3csvtagger.apply`): a hand-typed value overrides the layered
  candidates, flows through Apply into a real MP3, is recorded in the
  change log with Source "manual edit", and is undone by the snapshot;
  clearing the edit falls back to the layered value.
* R2 two-library sync (:mod:`mp3csvtagger.sync`): relative-path
  pairing, difference listing, a preview that copies only differing
  non-empty values (cover art included), and fingerprint pairing of
  the leftovers.
* R3 fingerprints (:mod:`mp3csvtagger.fingerprints`): ``fpcalc`` via a
  fake runner (no real fpcalc is installed on this machine and no test
  may depend on one), the size+mtime cache, same-recording groups, and
  AcoustID lookups via a fake opener (no live network calls).
* R4 consistency (:mod:`mp3csvtagger.consistency`): tags-vs-path
  mismatches, plus a source scan pinning the module's read-only
  imports.
* R5 completeness (:mod:`mp3csvtagger.library_report` additions).
* R6 jobs (:mod:`mp3csvtagger.jobs`): save/load/list/delete and the
  job <-> project conversions.

MP3 fixtures are built the way tests/test_engine.py builds them: a
minimal silent MPEG stream with a real ID3 header, in a temp folder.
"""

from __future__ import annotations

import csv
import json
import os
import sys
import types

import pytest
from mutagen.id3 import ID3

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "examples"))
from make_sample_mp3s import SILENT_MP3  # noqa: E402

from mp3csvtagger import fingerprints as fingerprints_mod  # noqa: E402
from mp3csvtagger import jobs as jobs_mod  # noqa: E402
from mp3csvtagger import sync as sync_mod  # noqa: E402
from mp3csvtagger.apply import apply_preview  # noqa: E402
from mp3csvtagger.consistency import (  # noqa: E402
    check_consistency,
    render_consistency_csv,
    render_consistency_text,
)
from mp3csvtagger.fingerprints import (  # noqa: E402
    Fingerprint,
    acoustid_lookup,
    fingerprint_file,
    same_recording_groups,
)
from mp3csvtagger.jobs import (  # noqa: E402
    delete_job,
    job_from_project,
    job_to_project,
    list_jobs,
    load_job,
    save_job,
)
from mp3csvtagger.library_report import (  # noqa: E402
    COMPLETENESS_FIELDS,
    album_completeness,
    render_completeness_text,
)
from mp3csvtagger.mp3files import Mp3File, scan  # noqa: E402
from mp3csvtagger.preview import (  # noqa: E402
    MANUAL_LAYER,
    MANUAL_SOURCE,
    build_preview,
)
from mp3csvtagger.project import Project, Role  # noqa: E402
from mp3csvtagger.sync import (  # noqa: E402
    build_sync_preview,
    default_sync_tags,
    pair_leftovers_by_fingerprint,
    pair_libraries,
    relative_key,
    tag_differences,
)
from mp3csvtagger.undo import undo_run  # noqa: E402

#: Two distinct fake PNG covers (header plus padding), as in
#: tests/test_v12_features.py — the bytes matter, not the image.
PNG_A = b"\x89PNG\r\n\x1a\n" + bytes(64)
PNG_B = b"\x89PNG\r\n\x1a\n" + bytes([7]) * 64

_FRAME_CLASSES = {}


def _frame(frame_id, value):
    """Build a mutagen text frame by frame id (cached class lookup)."""
    import mutagen.id3 as id3_mod

    cls = _FRAME_CLASSES.get(frame_id)
    if cls is None:
        cls = _FRAME_CLASSES[frame_id] = getattr(id3_mod, frame_id)
    return cls(text=[value])


def make_mp3(folder, name, *, tags=None, cover=None):
    """A real MP3 on disk with the given {frame id: value} tags / cover."""
    path = os.path.join(folder, name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as handle:
        handle.write(SILENT_MP3)
    audio = ID3()
    for frame_id, value in (tags or {}).items():
        audio.add(_frame(frame_id, value))
    if cover:
        from mutagen.id3 import APIC

        audio.add(APIC(encoding=3, mime="image/png", type=3, desc="", data=cover))
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


def read_log_rows(log_file):
    with open(log_file, encoding="utf-8") as handle:
        return list(csv.reader(handle))


def cover_bytes(path):
    frames = ID3(path).getall("APIC")
    return frames[0].data if frames else None


# ---------------------------------------------------------------------------
# R1 — manual preview edits
# ---------------------------------------------------------------------------

@pytest.fixture()
def manual_library(tmp_path):
    """One Rage track plus a CSV that would set its Genre to Rap Metal."""
    folder = str(tmp_path)
    song = make_mp3(
        folder, "01 Township Rebellion.mp3",
        tags={"TIT2": "Township Rebellion",
              "TPE1": "Rage Against the Machine", "TCON": "Rock"},
    )
    csv_path = make_csv(
        folder, "Sample1.csv", ["Lead Performer", "Genre"],
        [["Rage Against the Machine", "Rap Metal"]],
    )
    project = Project()
    project.add_mp3_path(folder)
    entry = project.add_csv_file(csv_path)
    set_roles(entry, **{"Lead Performer": Role.Match, "Genre": Role.Write})
    preview = build_preview(project)
    return folder, song, preview


def test_manual_edit_overrides_candidate_and_applies(manual_library, tmp_path):
    folder, song, preview = manual_library
    cell = preview.row_for_path(song).cells["Genre"]
    assert cell.value == "Rap Metal"  # the layered candidate, pre-edit

    cell.set_manual_edit("Hand Picked")
    manual = cell.manual_candidate
    assert manual is not None and manual.manual is True
    assert manual.csv_name == MANUAL_SOURCE == "manual edit"
    assert manual.layer == MANUAL_LAYER == 1_000_000
    assert manual.csv_row_index == -1
    assert cell.value == "Hand Picked"  # the edit is selected

    # A second edit replaces the first instead of stacking candidates.
    cell.set_manual_edit("Even Better")
    assert [c for c in cell.candidates if c.manual] == [cell.manual_candidate]
    assert cell.value == "Even Better"

    log_folder = str(tmp_path / "logs")
    result = apply_preview(preview, log_folder=log_folder)
    assert result.errors == []
    assert str(ID3(song)["TCON"].text[0]) == "Even Better"

    # The change log names the source of the written value.
    rows = read_log_rows(result.log_file)
    assert rows[0] == ["Timestamp", "File", "Tag Name", "ID3 Frame",
                       "Original/Old Value", "New Value", "Source"]
    genre_rows = [r for r in rows[1:] if r[2] == "Genre"]
    assert genre_rows[0][4] == "Rock" and genre_rows[0][5] == "Even Better"
    assert genre_rows[0][6] == "manual edit"

    # Undo is the ordinary tag snapshot: the manual value is reversed.
    undo_result = undo_run(result.undo_file)
    assert undo_result.restored == 1 and undo_result.errors == []
    assert str(ID3(song)["TCON"].text[0]) == "Rock"


def test_clear_manual_edit_reverts_to_layered_value(manual_library):
    _folder, song, preview = manual_library
    cell = preview.row_for_path(song).cells["Genre"]
    cell.set_manual_edit("Hand Picked")
    assert cell.value == "Hand Picked"
    cell.clear_manual_edit()
    assert cell.manual_candidate is None
    assert cell.value == "Rap Metal"  # last remaining candidate re-selected
    # Clearing again (nothing to clear) is a no-op, not an error.
    cell.clear_manual_edit()
    assert cell.value == "Rap Metal"


def test_manual_edit_on_cell_without_candidates(tmp_path):
    from mp3csvtagger.preview import Cell

    cell = Cell(tag_name="Genre", frame="TCON", old_value="Rock")
    cell.clear_manual_edit()  # no manual candidate: no-op
    cell.set_manual_edit("Solo")
    assert cell.value == "Solo" and cell.changed
    cell.clear_manual_edit()
    assert cell.candidates == [] and cell.value == "Rock"


# ---------------------------------------------------------------------------
# R2 — two-library sync
# ---------------------------------------------------------------------------

@pytest.fixture()
def twin_libraries(tmp_path):
    """A source library and its target twin, plus one unpaired file each."""
    source_root = str(tmp_path / "source")
    target_root = str(tmp_path / "target")
    # Same relative path, differing only in case (folder AND file name):
    # the pair must still be found.
    source_song = make_mp3(
        source_root, os.path.join("Artist", "Album", "01 Song.mp3"),
        tags={"TIT2": "Song", "TPE1": "Artist", "TALB": "Album",
              "TCON": "Rap Metal"},
    )
    target_song = make_mp3(
        target_root, os.path.join("artist", "album", "01 song.mp3"),
        tags={"TIT2": "Song", "TPE1": "Artist", "TALB": "Album",
              "TCON": "Rock", "TCOM": "The Composer"},
    )
    source_only = make_mp3(
        source_root, os.path.join("Artist", "Album", "02 Source Only.mp3"),
        tags={"TIT2": "Source Only", "TCON": "Metal"},
    )
    target_only = make_mp3(
        target_root, os.path.join("Artist", "Album", "03 Target Only.mp3"),
        tags={"TIT2": "Target Only", "TCON": "Jazz"},
    )
    return source_root, target_root, source_song, target_song, source_only, target_only


def test_relative_key_is_casefolded_with_forward_slashes():
    key = relative_key("/lib", os.path.join("/lib", "Artist", "Song.MP3"))
    assert key == "artist/song.mp3"


def test_sync_pairing_and_differences(twin_libraries):
    source_root, target_root, source_song, target_song, source_only, target_only = (
        twin_libraries
    )
    plan = pair_libraries(source_root, target_root)
    assert [(p.source_path, p.target_path) for p in plan.pairs] == [
        (source_song, target_song)
    ]
    assert plan.unpaired_source == [source_only]
    assert plan.unpaired_target == [target_only]

    source_files = scan([source_root])
    target_files = scan([target_root])

    # The default tag set is the union of text tags on paired sources.
    defaults = default_sync_tags(plan, source_files)
    assert set(defaults) == {"TIT2", "TPE1", "TALB", "TCON"}

    differences = tag_differences(
        plan, source_files, target_files,
        ["Title", "Genre", "Composer"], include_cover=False,
    )
    # Title agrees (not copied); Composer is empty on the source (never
    # copied — sync must not erase the target's value); only Genre
    # actually differs with a non-empty source value.
    assert differences == [{
        "target_path": target_song, "source_path": source_song,
        "tag": "Genre", "source_value": "Rap Metal", "target_value": "Rock",
    }]


def test_sync_preview_copies_only_differing_values_and_applies(twin_libraries, tmp_path):
    source_root, target_root, _ss, target_song, _so, target_only = twin_libraries
    plan = pair_libraries(source_root, target_root)
    source_files = scan([source_root])
    target_files = scan([target_root])

    preview = build_sync_preview(
        plan, source_files, target_files,
        ["Title", "Genre", "Composer"],
        include_cover=False, cover_dir=str(tmp_path / "covers"),
    )
    # Only the paired target appears; the unpaired target never does.
    assert [row.path for row in preview.rows] == [target_song]
    row = preview.row_for_path(target_song)
    assert set(row.cells) == {"Genre"}
    assert row.cells["Genre"].value == "Rap Metal"
    assert row.cells["Genre"].candidates[0].csv_name == "tag sync"

    result = apply_preview(preview, log_folder=str(tmp_path / "logs"))
    assert result.errors == []
    audio = ID3(target_song)
    assert str(audio["TCON"].text[0]) == "Rap Metal"
    assert str(audio["TCOM"].text[0]) == "The Composer"  # not erased
    # The unpaired target file was not touched at all.
    assert str(ID3(target_only)["TCON"].text[0]) == "Jazz"


def test_sync_cover_copy_swaps_target_cover_and_undo_restores(tmp_path):
    source_root = str(tmp_path / "source")
    target_root = str(tmp_path / "target")
    make_mp3(source_root, "Song.mp3",
             tags={"TIT2": "Song", "TCON": "Metal"}, cover=PNG_A)
    target_song = make_mp3(target_root, "Song.mp3",
                           tags={"TIT2": "Song", "TCON": "Metal"}, cover=PNG_B)
    plan = pair_libraries(source_root, target_root)
    source_files = scan([source_root])
    target_files = scan([target_root])

    differences = tag_differences(
        plan, source_files, target_files, ["Genre"], include_cover=True,
    )
    assert differences == [{
        "target_path": target_song, "source_path": plan.pairs[0].source_path,
        "tag": "Cover Art", "source_value": "[cover image]",
        "target_value": "[cover image]",
    }]

    cover_dir = str(tmp_path / "covers")
    preview = build_sync_preview(
        plan, source_files, target_files, ["Genre"],
        include_cover=True, cover_dir=cover_dir,
    )
    cell = preview.row_for_path(target_song).cells["Cover Art"]
    assert os.path.isabs(cell.value)
    assert os.path.dirname(cell.value) == os.path.abspath(cover_dir)
    assert os.path.basename(cell.value).startswith("sync-cover-")
    assert cell.value.endswith(".png")
    with open(cell.value, "rb") as handle:
        assert handle.read() == PNG_A  # the extracted image IS the source cover

    result = apply_preview(preview, log_folder=str(tmp_path / "logs"))
    assert result.errors == []
    assert cover_bytes(target_song) == PNG_A  # the cover actually swapped

    undo_result = undo_run(result.undo_file)
    assert undo_result.restored == 1 and undo_result.errors == []
    assert cover_bytes(target_song) == PNG_B  # ...and undo restores the old one


def test_pair_leftovers_by_fingerprint(twin_libraries):
    source_root, target_root, _ss, _ts, source_only, target_only = twin_libraries
    plan = pair_libraries(source_root, target_root)
    fingerprints = {
        source_only: Fingerprint(duration=200.0, fingerprint="SAMEAUDIO"),
        target_only: Fingerprint(duration=201.5, fingerprint="SAMEAUDIO"),
    }
    durations = {source_only: 200.0, target_only: 201.5}
    new_plan = pair_leftovers_by_fingerprint(plan, fingerprints, durations)
    assert (source_only, target_only) in [
        (p.source_path, p.target_path) for p in new_plan.pairs
    ]
    assert new_plan.unpaired_source == [] and new_plan.unpaired_target == []
    # The original plan is untouched (a NEW plan is returned).
    assert plan.unpaired_source == [source_only]

    # Same fingerprint but durations more than 2s apart: no pairing.
    far = pair_leftovers_by_fingerprint(
        plan, fingerprints, {source_only: 200.0, target_only: 205.0},
    )
    assert far.unpaired_source == [source_only]
    assert far.unpaired_target == [target_only]


# ---------------------------------------------------------------------------
# R3 — fingerprints
# ---------------------------------------------------------------------------

class FakeRunner:
    """A subprocess.run stand-in returning canned fpcalc JSON."""

    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def __call__(self, argv, **kwargs):
        self.calls.append((argv, kwargs))
        return types.SimpleNamespace(
            returncode=0,
            stdout=json.dumps(self.payload),
            stderr="",
        )


@pytest.fixture()
def cache_env(tmp_path, monkeypatch):
    monkeypatch.setenv("MP3CSVTAGGER_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("MP3CSVTAGGER_SETTINGS_DIR", str(tmp_path / "settings"))
    return tmp_path


def test_fingerprint_file_fake_runner_and_cache(tmp_path, cache_env, monkeypatch):
    monkeypatch.setattr(fingerprints_mod, "fpcalc_path", lambda: "/fake/fpcalc")
    path = make_mp3(str(tmp_path), "song.mp3", tags={"TIT2": "Song"})
    runner = FakeRunner({"duration": 12.5, "fingerprint": "FP123"})

    result = fingerprint_file(path, runner=runner)
    assert result == Fingerprint(duration=12.5, fingerprint="FP123")
    assert len(runner.calls) == 1
    argv, kwargs = runner.calls[0]
    assert argv == ["/fake/fpcalc", "-json", os.path.abspath(path)]
    assert kwargs == {"capture_output": True, "text": True}

    # Cache hit: the runner is not called again.
    assert fingerprint_file(path, runner=runner) == result
    assert len(runner.calls) == 1

    # Stale cache: the file changed (size + mtime), so it recomputes.
    with open(path, "ab") as handle:
        handle.write(b"x")
    stat = os.stat(path)
    os.utime(path, (stat.st_atime, stat.st_mtime + 10))
    assert fingerprint_file(path, runner=runner) == result
    assert len(runner.calls) == 2


def test_fingerprint_file_without_fpcalc_returns_none(tmp_path, cache_env, monkeypatch):
    monkeypatch.setattr(fingerprints_mod, "fpcalc_path", lambda: None)
    path = make_mp3(str(tmp_path), "song.mp3", tags={"TIT2": "Song"})
    runner = FakeRunner({"duration": 1.0, "fingerprint": "FP"})
    assert fingerprint_file(path, runner=runner) is None
    assert runner.calls == []  # never invoked when fpcalc is missing


def test_same_recording_groups_exclude_identical_tag_groups():
    def scanned(path, tags):
        return Mp3File(path=path, tags=tags)

    files = [
        scanned("/a.mp3", {"TIT2": "Song", "TCON": "Rock"}),
        scanned("/b.mp3", {"TIT2": "Song", "TCON": "Metal"}),  # differs
        scanned("/c.mp3", {"TIT2": "Other", "TCON": "Jazz"}),
        scanned("/d.mp3", {"TIT2": "Other", "TCON": "Jazz"}),  # identical to c
        scanned("/e.mp3", {"TIT2": "Lone"}),  # no fingerprint at all
    ]
    fps = {
        "/a.mp3": Fingerprint(100.0, "FP-ONE"),
        "/b.mp3": Fingerprint(100.0, "FP-ONE"),
        "/c.mp3": Fingerprint(50.0, "FP-TWO"),
        "/d.mp3": Fingerprint(50.0, "FP-TWO"),
    }
    groups = same_recording_groups(files, fps)
    # FP-TWO's files agree completely, so only FP-ONE is a finding.
    assert groups == [{
        "fingerprint": "FP-ONE", "duration": 100.0, "paths": ["/a.mp3", "/b.mp3"],
    }]


class FakeResponse:
    def __init__(self, body: bytes):
        self._body = body

    def read(self):
        return self._body


def _acoustid_body():
    return json.dumps({
        "status": "ok",
        "results": [
            {"score": 0.5, "recordings": [{
                "title": "Low Match", "artists": [{"name": "Someone"}],
                "releasegroups": [{"title": "Old Album",
                                   "firstreleasedate": {"year": 1990}}],
            }]},
            {"score": 0.9, "recordings": [{
                "title": "High Match", "artists": [{"name": "The Artist"}],
                "releasegroups": [{"title": "The Album",
                                   "firstreleasedate": "2001-05-01"}],
            }]},
        ],
    }).encode("utf-8")


def test_acoustid_lookup_with_fake_opener_and_sleeper(monkeypatch):
    monkeypatch.setattr(fingerprints_mod, "_last_lookup_at", None)
    urls = []
    sleeps = []

    def opener(url):
        urls.append(url)
        return FakeResponse(_acoustid_body())

    fp = Fingerprint(duration=123.0, fingerprint="FPX")
    matches = acoustid_lookup(fp, "TESTKEY", opener=opener, sleeper=sleeps.append)
    assert len(urls) == 1
    url = urls[0]
    assert url.startswith("https://api.acoustid.org/v2/lookup?")
    assert "client=TESTKEY" in url
    assert "duration=123" in url
    assert "fingerprint=FPX" in url
    assert "meta=recordings%2Breleasegroups%2Bcompress" in url
    # Sorted by score descending, with album/year parsed out.
    assert matches[0] == {"score": 0.9, "title": "High Match",
                          "artist": "The Artist", "album": "The Album",
                          "year": 2001}
    assert matches[1]["score"] == 0.5 and matches[1]["year"] == 1990
    assert sleeps == []  # first call in the process: nothing to space from

    # A second back-to-back call must sleep off the rest of the 1s gap.
    acoustid_lookup(fp, "TESTKEY", opener=opener, sleeper=sleeps.append)
    assert len(sleeps) == 1 and 0 < sleeps[0] <= 1.0


def test_acoustid_lookup_empty_key_raises_before_any_network():
    calls = []

    def opener(url):  # pragma: no cover - must never run
        calls.append(url)
        return FakeResponse(b"{}")

    with pytest.raises(ValueError, match="API key"):
        acoustid_lookup(
            Fingerprint(10.0, "FPX"), "",
            opener=opener, sleeper=lambda _s: None,
        )
    assert calls == []


def test_settings_round_trip(cache_env):
    from mp3csvtagger.fingerprints import (
        acoustid_api_key,
        load_settings,
        save_settings,
        settings_path,
    )

    assert acoustid_api_key() == ""  # nothing stored yet
    path = save_settings({"acoustid_api_key": "KEY123", "other": 1})
    assert path == settings_path() and path.name == "settings.json"
    assert load_settings() == {"acoustid_api_key": "KEY123", "other": 1}
    assert acoustid_api_key() == "KEY123"


# ---------------------------------------------------------------------------
# R4 — consistency (read-only)
# ---------------------------------------------------------------------------

PATTERN = "{Lead Performer}/{Album}/{Track Number} - {Title}"


def _consistency_files():
    def scanned(path, tags):
        return Mp3File(path=path, tags=tags)

    return [
        # Path and tags agree (artist case differs only — normalised equal).
        scanned("/music/Artist/Album/01 - Song.mp3",
                {"TPE1": "artist", "TALB": "Album", "TRCK": "01",
                 "TIT2": "Song"}),
        # Stored title disagrees with the path's title.
        scanned("/music/Artist/Album/02 - Real Title.mp3",
                {"TPE1": "Artist", "TALB": "Album", "TRCK": "02",
                 "TIT2": "Different Title"}),
        # The title tag is EMPTY while the path names one: a mismatch.
        scanned("/music/Artist/Album/03 - Missing.mp3",
                {"TPE1": "Artist", "TALB": "Album", "TRCK": "03"}),
        # The path does not fit the pattern at all: unmatched, unchecked.
        scanned("/music/loose-file.mp3", {"TIT2": "Loose"}),
    ]


def test_check_consistency_mismatches_and_unmatched():
    result = check_consistency(_consistency_files(), PATTERN, root="/music")
    assert result.files_checked == 4
    assert result.checked == 3
    assert result.unmatched == ["/music/loose-file.mp3"]

    by_tag = {(m.path, m.tag): m for m in result.mismatches}
    title = by_tag[("/music/Artist/Album/02 - Real Title.mp3", "Title")]
    assert title.path_value == "Real Title" and title.tag_value == "Different Title"
    missing = by_tag[("/music/Artist/Album/03 - Missing.mp3", "Title")]
    assert missing.path_value == "Missing" and missing.tag_value == ""
    assert len(result.mismatches) == 2  # the agreeing file produced none


def test_render_consistency_outputs():
    result = check_consistency(_consistency_files(), PATTERN, root="/music")
    text = render_consistency_text(result, PATTERN)
    assert PATTERN in text
    assert "Mismatches: 2" in text
    assert "Real Title" in text and "loose-file.mp3" in text

    rows = list(csv.reader(render_consistency_csv(result).splitlines()))
    assert rows[0] == ["Path", "Tag", "From Path", "In Tags"]
    assert ["/music/Artist/Album/02 - Real Title.mp3", "Title",
            "Real Title", "Different Title"] in rows


def test_consistency_module_is_structurally_read_only():
    # The read-only guarantee is structural: the module may not import
    # anything that can write tags. Pin it by scanning the source.
    path = os.path.join(
        os.path.dirname(__file__), "..", "src", "mp3csvtagger", "consistency.py",
    )
    with open(path, encoding="utf-8") as handle:
        source = handle.read()
    for forbidden in (".apply", ".preview", ".undo",
                      "import apply", "import preview", "import undo"):
        assert forbidden not in source


# ---------------------------------------------------------------------------
# R5 — album completeness
# ---------------------------------------------------------------------------

def test_album_completeness_counts_and_percents():
    def scanned(path, tags, cover=False):
        return Mp3File(path=path, tags=tags, has_cover=cover)

    full = {"TIT2": "One", "TPE1": "Art", "TALB": "Alb", "TYER": "2000",
            "TCON": "Rock", "TRCK": "1"}
    # Year via TDRC instead of TYER still counts as having a year.
    sparse = {"TIT2": "Two", "TPE1": "Art", "TALB": "Alb", "TDRC": "2001"}
    files = [
        scanned("/1.mp3", full, cover=True),
        scanned("/2.mp3", sparse),
        scanned("/3.mp3", {"TIT2": "Loose"}),  # no album at all
    ]
    data = album_completeness(files)

    assert [name for name, _frame in COMPLETENESS_FIELDS] == [
        "Title", "Lead Performer", "Album", "Year", "Genre",
        "Track Number", "Cover Art",
    ]
    by_album = {album["album"]: album for album in data["albums"]}
    alb = by_album["Alb"]
    assert alb["artist"] == "Art" and alb["files"] == 2
    assert alb["fields"]["Title"] == {"count": 2, "percent": 100.0}
    assert alb["fields"]["Year"] == {"count": 2, "percent": 100.0}  # TYER + TDRC
    assert alb["fields"]["Genre"] == {"count": 1, "percent": 50.0}
    assert alb["fields"]["Cover Art"] == {"count": 1, "percent": 50.0}
    assert alb["percent"] == pytest.approx((100.0 * 4 + 50.0 * 3) / 7)

    no_album = by_album["(no album)"]
    assert no_album["files"] == 1 and no_album["fields"]["Album"]["count"] == 0

    summary = data["summary"]
    assert summary["files"] == 3 and summary["albums"] == 2
    assert summary["fields"]["Title"]["count"] == 3

    text = render_completeness_text(data)
    assert "Album completeness" in text and "(no album)" in text
    assert "Alb" in text and "Cover Art" in text


# ---------------------------------------------------------------------------
# R6 — jobs
# ---------------------------------------------------------------------------

def test_jobs_round_trip_and_project_equivalence(tmp_path, monkeypatch):
    monkeypatch.setenv("MP3CSVTAGGER_JOBS_DIR", str(tmp_path / "jobs"))
    folder = str(tmp_path)
    csv_path = make_csv(folder, "roles.csv", ["Lead Performer", "Genre"],
                        [["Artist", "Metal"]])
    project = Project()
    project.add_mp3_path("/music")
    entry = project.add_csv_file(csv_path)
    set_roles(entry, **{"Lead Performer": Role.Match, "Genre": Role.Write})

    layers = [{"pattern": "{Title}", "root": "/music", "use_path": False}]
    job = job_from_project("Weekly Fix", project, pattern_layers=layers)
    path = save_job(job)
    assert path.name == "Weekly-Fix.json" and path.is_file()
    assert list_jobs() == ["Weekly Fix"]

    loaded = load_job("Weekly Fix")
    assert loaded.to_dict() == job.to_dict()
    assert loaded.pattern_layers == layers
    assert loaded.csv_entries[0].path == csv_path

    # The job converts back to an equivalent project.
    rebuilt = job_to_project(loaded)
    assert rebuilt.to_dict() == project.to_dict()

    assert delete_job("Weekly Fix") is True
    assert list_jobs() == []
    assert delete_job("Weekly Fix") is False  # already gone: not an error
    with pytest.raises(FileNotFoundError):
        load_job("Weekly Fix")


def test_jobs_dir_env_override(tmp_path, monkeypatch):
    monkeypatch.setenv("MP3CSVTAGGER_JOBS_DIR", str(tmp_path / "elsewhere"))
    assert jobs_mod.jobs_dir() == tmp_path / "elsewhere"
    assert (tmp_path / "elsewhere").is_dir()  # created on demand
