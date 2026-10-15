"""Tests for tag-snapshot undo (``mp3csvtagger.undo``).

Undo stores *tag snapshots only* — never a copy of the audio — so these
tests build real MP3 files (a minimal MPEG frame body, the same shape
the engine tests use), snapshot their tags, mangle the tags, and check
that restore puts exactly the snapshotted frames back while leaving the
frames undo does not own (cover art, private frames) alone.
"""

from __future__ import annotations

import gzip
import json

import pytest
from mutagen.id3 import (
    APIC,
    ID3,
    PRIV,
    TCON,
    TIT2,
    TPE1,
    TXXX,
    ID3NoHeaderError,
)

from mp3csvtagger.undo import (
    make_entry,
    read_undo_file,
    restore_entry,
    snapshot_frames,
    undo_run,
    write_undo_file,
)

# One valid MPEG-1 Layer III frame header + zeroed payload, repeated:
# enough for mutagen / tag editors to treat the file as an MP3.
_FRAME = bytes([0xFF, 0xFB, 0x90, 0x00]) + bytes(413)
AUDIO_BODY = _FRAME * 20

FAKE_JPEG = b"\xff\xd8\xff\xe0fake-jpeg-data"
PRIV_DATA = b"private-data"


def make_tagged_mp3(folder, name="song.mp3"):
    """Write a real MP3 with TIT2/TPE1, a custom TXXX, APIC and PRIV."""
    path = str(folder / name)
    with open(path, "wb") as handle:
        handle.write(AUDIO_BODY)
    audio = ID3()
    audio.add(TIT2(text=["Before Title"]))
    audio.add(TPE1(text=["Before Artist"]))
    audio.add(TXXX(encoding=3, desc="Mood", text=["Happy"]))
    audio.add(
        APIC(
            encoding=3,
            mime="image/jpeg",
            type=3,  # front cover
            desc="cover",
            data=FAKE_JPEG,
        )
    )
    audio.add(PRIV(owner="test@example.com", data=PRIV_DATA))
    audio.save(path)
    return path


def make_bare_mp3(folder, name="bare.mp3"):
    """Write a real MP3 body with no ID3 header at all."""
    path = str(folder / name)
    with open(path, "wb") as handle:
        handle.write(AUDIO_BODY)
    return path


def test_restore_brings_back_snapshot_and_leaves_apic_and_priv_alone(tmp_path):
    path = make_tagged_mp3(tmp_path)

    # Snapshot directly too, to pin down the APIC/PRIV exclusion rules.
    snapshotted = snapshot_frames(ID3(path))
    keys = [item["key"] for item in snapshotted]
    assert "TIT2" in keys and "TPE1" in keys and "TXXX:Mood" in keys
    assert not any(key.startswith("APIC") for key in keys)  # big, untouched
    assert not any(key.startswith("PRIV") for key in keys)  # never ours
    with_apic = snapshot_frames(ID3(path), include_apic=True)
    keys_with_apic = [item["key"] for item in with_apic]
    assert any(key.startswith("APIC") for key in keys_with_apic)
    # PRIV is still skipped even when APIC is explicitly included.
    assert not any(key.startswith("PRIV") for key in keys_with_apic)

    entry = make_entry(path)
    assert entry["had_no_header"] is False
    assert entry["apic_included"] is False
    assert entry["path"] == path

    # Mangle the tags: change a frame, delete one, add a new one.
    audio = ID3(path)
    audio.delall("TIT2")
    audio.add(TIT2(text=["Changed Title"]))
    audio.delall("TXXX:Mood")
    audio.add(TCON(text=["Rock"]))
    audio.save(path)

    # Editing changed the file's mtime, so the guard would skip this
    # without force (that guard itself is test 3); here we mean it.
    status, _message = restore_entry(entry, force=True)
    assert status == "restored"

    restored = ID3(path)
    # Tags are exactly as snapshotted…
    assert str(restored["TIT2"].text[0]) == "Before Title"
    assert str(restored["TPE1"].text[0]) == "Before Artist"
    assert str(restored["TXXX:Mood"].text[0]) == "Happy"
    assert "TCON" not in restored  # the frame added after snapshot is gone
    # (PRIV's HashKey embeds its data, so it is matched by prefix below
    # rather than listed in the exact key set.)
    assert set(restored.keys()) - {
        key for key in restored.keys() if key.startswith("PRIV:")
    } == {"TIT2", "TPE1", "TXXX:Mood", "APIC:cover"}
    # …and the frames undo does not own survived untouched.
    assert restored["APIC:cover"].data == FAKE_JPEG
    priv_frames = [f for f in restored.values() if f.FrameID == "PRIV"]
    assert len(priv_frames) == 1
    assert priv_frames[0].data == PRIV_DATA


def test_undo_of_no_header_file_removes_tag_entirely(tmp_path):
    path = make_bare_mp3(tmp_path)

    entry = make_entry(path)
    assert entry["had_no_header"] is True
    assert entry["frames"] == []

    # Tag the previously bare file.
    audio = ID3()
    audio.add(TIT2(text=["Added Later"]))
    audio.save(path)
    assert str(ID3(path)["TIT2"].text[0]) == "Added Later"

    status, _message = restore_entry(entry, force=True)
    assert status == "restored"

    # The "before" state had no header, so there is no tag again.
    with pytest.raises(ID3NoHeaderError):
        ID3(path)
    # The audio body itself was never copied or harmed.
    with open(path, "rb") as handle:
        assert handle.read() == AUDIO_BODY


def test_changed_file_is_skipped_unless_forced(tmp_path):
    path = make_tagged_mp3(tmp_path)
    entry = make_entry(path)

    # Change a tag, then change the file's size as an outside edit would.
    audio = ID3(path)
    audio.delall("TIT2")
    audio.add(TIT2(text=["Changed Title"]))
    audio.save(path)
    with open(path, "ab") as handle:
        handle.write(b"extra")

    status, message = restore_entry(entry)
    assert status == "skipped"
    assert path in message
    # A skipped restore changes nothing.
    assert str(ID3(path)["TIT2"].text[0]) == "Changed Title"

    status, _message = restore_entry(entry, force=True)
    assert status == "restored"
    assert str(ID3(path)["TIT2"].text[0]) == "Before Title"


def test_undo_file_round_trip_and_undo_run_restores(tmp_path):
    path = make_tagged_mp3(tmp_path)
    entry = make_entry(path)
    undo_path = str(tmp_path / "undo.json.gz")

    write_undo_file(undo_path, [entry])

    payload = read_undo_file(undo_path)
    assert payload["format"] == "mp3csvtagger-undo"
    assert payload["version"] == 1
    assert payload["created"]  # an ISO timestamp was recorded
    assert payload["files"] == [entry]

    # A file that is not one of ours is rejected, not silently applied.
    bogus_path = str(tmp_path / "bogus.json.gz")
    with gzip.open(bogus_path, "wt", encoding="utf-8") as handle:
        json.dump({"format": "something-else", "files": []}, handle)
    with pytest.raises(ValueError):
        read_undo_file(bogus_path)

    # Change a tag, then undo the whole run from the file on disk.
    audio = ID3(path)
    audio.delall("TIT2")
    audio.add(TIT2(text=["Changed Title"]))
    audio.save(path)

    result = undo_run(undo_path, force=True)
    assert result.restored == 1
    assert result.skipped == []
    assert result.errors == []
    assert result.messages  # every file got a human-readable message
    assert str(ID3(path)["TIT2"].text[0]) == "Before Title"
    # APIC was excluded from the snapshot and is still there, untouched.
    assert ID3(path)["APIC:cover"].data == FAKE_JPEG
