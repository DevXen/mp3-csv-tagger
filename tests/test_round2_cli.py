"""CLI-level tests for the round-2 commands (Brief B integration).

Covered here, command by command, driving :func:`mp3csvtagger.cli.main`
the way a shell user would:

* ``sync-tags`` — a dry run that changes nothing, then an ``--apply``
  run whose tags (and cover) actually land, with a change log whose
  Source column says "tag sync" and a snapshot undo file beside it.
* ``report`` — ``--pattern`` finds a planted tags-vs-path mismatch
  (and writes it as CSV with ``--out``), ``--completeness`` prints the
  album completeness section, and the flag-free report is unchanged.
* ``report --same-recordings`` — the graceful no-fpcalc path, plus a
  ``--unify-from`` dry run / apply pair driven by fake fingerprints
  (monkeypatched onto the fingerprints module — no real fpcalc, no
  network).
* ``acoustid`` — an empty API key exits 2 *before* any network use:
  the lookup function is monkeypatched to raise if it is ever called.
* ``fingerprint-status`` — runs and reports fpcalc + the cache.
* ``jobs`` / ``job-save`` / ``job-run`` — save a project as a job, add
  a pattern layer to it (the GUI-side state the CLI stores none of),
  then run it dry and for real.

Plus the feasible headless GUI checks: the gui module compiles and
imports, its pure drop/paste path helpers behave, the player opener
shells out correctly, and — only when a display exists (xvfb) — the
App window constructs with the round-2 widgets present.

MP3 fixtures follow tests/test_round2_engine.py: a minimal silent
MPEG stream with a real ID3 header, in a temp folder.
"""

from __future__ import annotations

import csv
import glob
import os
import sys

import pytest
from mutagen.id3 import ID3

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "examples"))
from make_sample_mp3s import SILENT_MP3  # noqa: E402

from mp3csvtagger import cli  # noqa: E402
from mp3csvtagger import fingerprints as fingerprints_mod  # noqa: E402
from mp3csvtagger.fingerprints import Fingerprint  # noqa: E402
from mp3csvtagger.jobs import load_job, save_job  # noqa: E402
from mp3csvtagger.project import Project, Role  # noqa: E402

#: A fake PNG cover (header plus padding), as in the engine tests.
PNG_A = b"\x89PNG\r\n\x1a\n" + bytes(64)

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


def tag_value(path, frame_id):
    audio = ID3(path)
    frame = audio.get(frame_id)
    return str(frame.text[0]) if frame is not None else None


def cover_bytes(path):
    frames = ID3(path).getall("APIC")
    return frames[0].data if frames else None


@pytest.fixture()
def state_env(tmp_path, monkeypatch):
    """Point every round-2 state directory at the temp folder.

    Jobs, the fingerprint cache and the settings file all honour
    environment overrides; without this fixture the tests would read
    (or write) the developer's real ~/.mp3csvtagger state — the
    AcoustID tests in particular must see *no* saved API key.
    """
    monkeypatch.setenv("MP3CSVTAGGER_JOBS_DIR", str(tmp_path / "jobs"))
    monkeypatch.setenv("MP3CSVTAGGER_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("MP3CSVTAGGER_SETTINGS_DIR", str(tmp_path / "settings"))
    return tmp_path


# ---------------------------------------------------------------------------
# sync-tags
# ---------------------------------------------------------------------------

@pytest.fixture()
def twin_libraries(tmp_path):
    """A source library and its target twin (one paired song each)."""
    source_root = str(tmp_path / "source")
    target_root = str(tmp_path / "target")
    source_song = make_mp3(
        source_root, "Song.mp3",
        tags={"TIT2": "Song", "TPE1": "Artist", "TCON": "Rap Metal"},
        cover=PNG_A,
    )
    target_song = make_mp3(
        target_root, "Song.mp3",
        tags={"TIT2": "Song", "TPE1": "Artist", "TCON": "Rock"},
    )
    return source_root, target_root, source_song, target_song


def test_sync_tags_dry_run_then_apply(twin_libraries, tmp_path, capsys):
    source_root, target_root, _source_song, target_song = twin_libraries
    logs = str(tmp_path / "logs")
    preview_csv = str(tmp_path / "preview.csv")

    # Dry run: the pairing and the differences are reported, a preview
    # CSV is written — and the target file is NOT touched.
    rc = cli.main([
        "sync-tags", "--source", source_root, "--target", target_root,
        "--log-folder", logs, "--out", preview_csv,
    ])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Paired files  : 1" in out
    assert "Differences   : 2" in out  # Genre + Cover Art
    assert "Dry run" in out
    assert os.path.isfile(preview_csv)
    assert tag_value(target_song, "TCON") == "Rock"
    assert cover_bytes(target_song) is None

    # Apply: the genre and the cover land on the target, the change
    # log's Source column names "tag sync", and a snapshot undo file
    # exists for the run.
    rc = cli.main([
        "sync-tags", "--source", source_root, "--target", target_root,
        "--log-folder", logs, "--apply",
    ])
    assert rc == 0
    assert tag_value(target_song, "TCON") == "Rap Metal"
    assert cover_bytes(target_song) == PNG_A
    undo_files = glob.glob(os.path.join(logs, "*.undo"))
    log_files = glob.glob(os.path.join(logs, "*.log.csv"))
    assert undo_files and log_files
    with open(log_files[0], encoding="utf-8") as handle:
        rows = list(csv.reader(handle))
    assert rows[0][-1] == "Source"
    assert {row[6] for row in rows[1:]} == {"tag sync"}


def test_sync_tags_fingerprint_pairing_without_fpcalc_is_graceful(
    twin_libraries, tmp_path, capsys, monkeypatch
):
    source_root, target_root, _s, _t = twin_libraries
    monkeypatch.setattr(fingerprints_mod, "fpcalc_path", lambda: None)
    rc = cli.main([
        "sync-tags", "--source", source_root, "--target", target_root,
        "--fingerprint-pairing", "--log-folder", str(tmp_path / "logs"),
    ])
    assert rc == 0
    assert "fpcalc was not detected" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# report extensions
# ---------------------------------------------------------------------------

@pytest.fixture()
def consistency_library(tmp_path):
    """Two files under Artist/Album; one title disagrees with its path."""
    root = str(tmp_path / "music")
    good = make_mp3(
        root, os.path.join("Artist", "Album", "01 - Song.mp3"),
        tags={"TIT2": "Song", "TPE1": "Artist", "TALB": "Album", "TRCK": "01"},
    )
    bad = make_mp3(
        root, os.path.join("Artist", "Album", "02 - Real Title.mp3"),
        tags={"TIT2": "Different Title", "TPE1": "Artist",
              "TALB": "Album", "TRCK": "02"},
    )
    return root, good, bad


PATTERN = "{Lead Performer}/{Album}/{Track Number} - {Title}"


def test_report_pattern_finds_planted_mismatch(consistency_library, capsys):
    root, _good, bad = consistency_library
    rc = cli.main([
        "report", "--folder", root, "--pattern", PATTERN, "--root", root,
    ])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Tags vs path consistency" in out
    assert "Mismatches: 1" in out
    assert "Real Title" in out and "Different Title" in out
    assert bad in out


def test_report_pattern_out_csv(consistency_library, tmp_path):
    root, _good, bad = consistency_library
    out_csv = str(tmp_path / "consistency.csv")
    rc = cli.main([
        "report", "--folder", root, "--pattern", PATTERN, "--root", root,
        "--out", out_csv,
    ])
    assert rc == 0
    with open(out_csv, encoding="utf-8") as handle:
        rows = list(csv.reader(handle))
    assert rows[0] == ["Path", "Tag", "From Path", "In Tags"]
    assert [bad, "Title", "Real Title", "Different Title"] in rows


def test_report_completeness_prints_album_rows(consistency_library, capsys):
    root, _good, _bad = consistency_library
    rc = cli.main(["report", "--folder", root, "--completeness"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Duplicates:" in out  # the plain report is still there
    assert "Album completeness" in out
    assert "Album by Artist (2 file(s)" in out
    assert "Cover Art: 0/2 (0.0%)" in out


def test_report_same_recordings_without_fpcalc(consistency_library, capsys, monkeypatch):
    root, _good, _bad = consistency_library
    monkeypatch.setattr(fingerprints_mod, "fpcalc_path", lambda: None)
    rc = cli.main(["report", "--folder", root, "--same-recordings"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "fpcalc was not detected" in out
    assert "Duplicates:" in out  # the rest of the report still prints


def test_report_same_recordings_unify_from(tmp_path, capsys, monkeypatch):
    folder = str(tmp_path / "music")
    source = make_mp3(
        folder, "a.mp3",
        tags={"TIT2": "Song", "TPE1": "Artist", "TCON": "Rock"},
    )
    other = make_mp3(
        folder, "b.mp3",
        tags={"TIT2": "Song", "TPE1": "Artist", "TCON": "Metal"},
    )
    fake_fps = {
        source: Fingerprint(duration=100.0, fingerprint="SAMEFP"),
        other: Fingerprint(duration=100.0, fingerprint="SAMEFP"),
    }
    monkeypatch.setattr(fingerprints_mod, "fpcalc_path", lambda: "/fake/fpcalc")
    monkeypatch.setattr(
        fingerprints_mod, "fingerprints_for",
        lambda files, progress=None: fake_fps,
    )
    logs = str(tmp_path / "logs")

    # The report lists the group…
    rc = cli.main(["report", "--folder", folder, "--same-recordings"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Same recordings (audio fingerprint)" in out
    assert source in out and other in out

    # …a unify dry run changes nothing…
    rc = cli.main([
        "report", "--folder", folder, "--same-recordings",
        "--unify-from", source,
    ])
    assert rc == 0
    assert "Dry run" in capsys.readouterr().out
    assert tag_value(other, "TCON") == "Metal"

    # …and applying it copies the source file's tags onto the other
    # group member, with a snapshot undo for the run.
    rc = cli.main([
        "report", "--folder", folder, "--same-recordings",
        "--unify-from", source, "--apply", "--log-folder", logs,
    ])
    assert rc == 0
    assert tag_value(other, "TCON") == "Rock"
    assert glob.glob(os.path.join(logs, "*.undo"))


# ---------------------------------------------------------------------------
# acoustid / fingerprint-status
# ---------------------------------------------------------------------------

def test_acoustid_empty_key_exits_2_without_network(tmp_path, state_env, monkeypatch):
    folder = str(tmp_path / "music")
    make_mp3(folder, "song.mp3", tags={"TIT2": "Song"})

    def forbidden_lookup(*_args, **_kwargs):  # pragma: no cover
        raise AssertionError("acoustid_lookup must not be called without a key")

    monkeypatch.setattr(fingerprints_mod, "acoustid_lookup", forbidden_lookup)
    # With files to look up, and even with no files at all: the key
    # check comes first and the exit code is 2 either way.
    assert cli.main(["acoustid", "--folder", folder]) == 2
    assert cli.main(["acoustid"]) == 2


def test_fingerprint_status_runs(state_env, capsys):
    assert cli.main(["fingerprint-status"]) == 0
    out = capsys.readouterr().out
    assert "fpcalc:" in out
    assert "Fingerprint cache:" in out
    assert "fingerprint-cache.json" in out


# ---------------------------------------------------------------------------
# jobs / job-save / job-run
# ---------------------------------------------------------------------------

def test_jobs_save_and_run_flow(tmp_path, state_env, capsys):
    folder = str(tmp_path / "music")
    song = make_mp3(
        folder, "01 - Song.mp3",
        tags={"TPE1": "Artist", "TCON": "Rock"},  # no Title: the pattern adds it
    )
    csv_path = make_csv(
        folder, "tags.csv", ["Lead Performer", "Genre"], [["Artist", "Metal"]]
    )
    project = Project()
    project.add_mp3_path(folder)
    entry = project.add_csv_file(csv_path)
    set_roles(entry, **{"Lead Performer": Role.Match, "Genre": Role.Write})
    project_file = str(tmp_path / "proj.mp3p.json")
    project.save(project_file)

    # job-save stores the project as a named job (with the printed
    # note that CLI-saved jobs carry no pattern layers)…
    assert cli.main(["job-save", "Weekly Fix", project_file]) == 0
    out = capsys.readouterr().out
    assert "pattern layers are GUI-side state" in out
    assert cli.main(["jobs"]) == 0
    assert "Weekly Fix" in capsys.readouterr().out

    # …then a pattern layer is added to the saved job (as the GUI
    # would store it) so job-run must apply it after the CSV layers.
    job = load_job("Weekly Fix")
    assert job.pattern_layers == []
    job.pattern_layers = [
        {"pattern": "{Track Number} - {Title}", "root": "", "use_path": False}
    ]
    save_job(job)

    logs = str(tmp_path / "logs")
    # Dry run first: both the CSV change and the pattern change show,
    # and the file is untouched.
    assert cli.main(["job-run", "Weekly Fix"]) == 0
    assert "Dry run" in capsys.readouterr().out
    assert tag_value(song, "TCON") == "Rock"
    assert tag_value(song, "TIT2") is None

    # Apply: both layers land, and the run leaves a snapshot undo.
    assert cli.main(["job-run", "Weekly Fix", "--apply",
                     "--log-folder", logs]) == 0
    assert tag_value(song, "TCON") == "Metal"
    assert tag_value(song, "TIT2") == "Song"
    assert glob.glob(os.path.join(logs, "*.undo"))


def test_job_run_unknown_job_is_a_clean_error(state_env):
    with pytest.raises(SystemExit, match="Job not found"):
        cli.main(["job-run", "No Such Job"])


# ---------------------------------------------------------------------------
# GUI — the feasible headless checks (no visual verification claimed)
# ---------------------------------------------------------------------------

def test_gui_module_imports_and_pure_helpers():
    pytest.importorskip("tkinter")
    from mp3csvtagger import gui

    # The tkinterdnd2 import is guarded: the flag exists either way,
    # and the module imported fine in this environment regardless.
    assert isinstance(gui._DND_AVAILABLE, bool)
    # Drop strings: braced paths keep their spaces, plain paths split.
    assert gui._split_dnd_data("{/music/My Songs/a.mp3} /music/b.mp3") == [
        "/music/My Songs/a.mp3", "/music/b.mp3",
    ]
    assert gui._split_dnd_data("") == []
    # Pasted paths: one per line, quotes and blank lines tolerated.
    assert gui.split_pasted_paths('"/music/a.mp3"\n\n/music/b.mp3 \n') == [
        "/music/a.mp3", "/music/b.mp3",
    ]


def test_gui_open_in_player_uses_platform_opener(monkeypatch):
    pytest.importorskip("tkinter")
    from mp3csvtagger import gui

    calls = []
    monkeypatch.setattr(
        gui.subprocess, "Popen", lambda argv, **_kw: calls.append(argv)
    )
    gui.open_in_player("/music/song.mp3")
    if sys.platform == "win32":
        # os.startfile is Windows-only; nothing to assert via Popen.
        assert calls == []
    elif sys.platform == "darwin":
        assert calls == [["open", "/music/song.mp3"]]
    else:
        assert calls == [["xdg-open", "/music/song.mp3"]]


def test_gui_app_constructs_with_round2_widgets():
    # Constructing a real window needs a display; under a plain
    # headless run this skips (run the suite under `xvfb-run` to
    # exercise it). It proves construction only — not that anything
    # was visually verified.
    if not os.environ.get("DISPLAY"):
        pytest.skip("no display available (run under xvfb-run)")
    pytest.importorskip("tkinter")
    from mp3csvtagger import gui

    app = gui.App()
    try:
        app.update_idletasks()
        # Round-2 widgets exist: the jobs row, the preview grouping
        # toggle, the inline-edit state.
        assert hasattr(app, "job_combo")
        assert hasattr(app, "group_by_album")
        assert hasattr(app, "acoustid_key_var")
        assert app.group_by_album.get() is False
        tab_titles = [
            app.tabs.tab(tab_id, "text") for tab_id in app.tabs.tabs()
        ]
        assert tab_titles[:3] == ["Files", "CSV Files", "Preview"]
    finally:
        app.destroy()
