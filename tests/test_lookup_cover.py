"""Tests for the opt-in MusicBrainz lookup and the cover-art helpers.

Everything runs offline: the MusicBrainz tests inject a fake ``opener``
returning canned JSON bytes, and a recording fake ``sleeper`` so the
rate-limit waits are asserted without actually sleeping.
"""

from __future__ import annotations

import json
import os

import pytest

from mp3csvtagger.coverart import (
    COVER_TAG_NAME,
    cover_display,
    make_cover_frame,
    mime_for_image,
    resolve_image_path,
)
from mp3csvtagger.mp3files import Mp3File
from mp3csvtagger.musicbrainz import (
    USER_AGENT,
    LookupError,
    fields_from_recording,
    fill_missing,
    search_recording,
)

#: Canned MusicBrainz recording, as ``fields_from_recording`` /
#: ``search_recording`` would receive it.
RECORDING = {
    "title": "Township Rebellion",
    "first-release-date": "1992-09-29",
    "releases": [{"title": "Rage Against the Machine", "date": "1992-09-29"}],
    "tags": [
        {"name": "rock", "count": 3},
        {"name": "rap metal", "count": 9},
    ],
}

CANNED_BYTES = json.dumps({"recordings": [RECORDING]}).encode("utf-8")

# A tiny (not necessarily valid-image) payload: the helpers only carry the
# bytes through, so the tests check the round-trip, not image decoding.
PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"tiny-fake-png-payload"


class FakeOpener:
    """Callable ``opener(url, headers, timeout) -> bytes`` recording calls."""

    def __init__(self, body=CANNED_BYTES):
        self.body = body
        self.calls = []

    def __call__(self, url, headers, timeout):
        self.calls.append((url, headers, timeout))
        return self.body


class FakeSleeper:
    """Callable stand-in for ``time.sleep`` recording the intervals slept."""

    def __init__(self):
        self.calls = []

    def __call__(self, seconds):
        self.calls.append(seconds)


# ---------------------------------------------------------------------------
# MusicBrainz: search_recording
# ---------------------------------------------------------------------------

def test_search_recording_url_headers_and_first_result():
    opener = FakeOpener()
    result = search_recording("Rage Against the Machine", "Township Rebellion",
                              opener=opener)
    assert result == RECORDING
    assert len(opener.calls) == 1
    url, headers, timeout = opener.calls[0]
    assert "musicbrainz.org" in url
    assert "/recording/" in url
    assert "fmt=json" in url
    assert 'recording:"Township Rebellion"' in url
    assert 'artist:"Rage Against the Machine"' in url
    assert headers["User-Agent"] == USER_AGENT
    assert timeout == 20


def test_search_recording_escapes_embedded_quotes():
    opener = FakeOpener()
    search_recording('The "Quoted" Band', 'Say "Hi"', opener=opener)
    url, _headers, _timeout = opener.calls[0]
    assert '\\"' in url  # embedded quotes are escaped, not left bare


def test_search_recording_no_recordings_returns_none():
    opener = FakeOpener(body=json.dumps({"recordings": []}).encode("utf-8"))
    assert search_recording("Nobody", "Nothing", opener=opener) is None


def test_search_recording_bad_json_raises_lookup_error():
    opener = FakeOpener(body=b"this is not json")
    with pytest.raises(LookupError):
        search_recording("Someone", "Something", opener=opener)


def test_search_recording_http_failure_raises_lookup_error():
    def failing_opener(url, headers, timeout):
        raise OSError("simulated HTTP 503")

    with pytest.raises(LookupError):
        search_recording("Someone", "Something", opener=failing_opener)


# ---------------------------------------------------------------------------
# MusicBrainz: fields_from_recording
# ---------------------------------------------------------------------------

def test_fields_from_recording():
    fields = fields_from_recording(
        RECORDING, ["Album", "Recording Date", "Year", "Genre"]
    )
    assert fields == {
        "Album": "Rage Against the Machine",
        "Recording Date": "1992-09-29",
        "Year": "1992",
        # Highest-count tag wins (9 > 3), not the first tag.
        "Genre": "rap metal",
    }


def test_fields_from_recording_only_wanted_fields():
    assert fields_from_recording(RECORDING, ["Year"]) == {"Year": "1992"}
    assert fields_from_recording(RECORDING, []) == {}
    assert fields_from_recording(None, ["Album"]) == {}


def test_fields_from_recording_date_falls_back_to_release_date():
    recording = {"releases": [{"title": "Some Album", "date": "2001-05-06"}]}
    fields = fields_from_recording(recording, ["Recording Date", "Year"])
    assert fields == {"Recording Date": "2001-05-06", "Year": "2001"}


# ---------------------------------------------------------------------------
# MusicBrainz: fill_missing
# ---------------------------------------------------------------------------

def _file(path, **tags):
    return Mp3File(path=path, tags=tags)


def test_fill_missing_only_fills_empty_fields_and_skips_and_sleeps():
    opener = FakeOpener()
    sleeper = FakeSleeper()
    progress_calls = []

    # Genre is already set -> must NOT be overwritten by "rap metal";
    # Album is empty -> filled.
    needs_album = _file(
        "/music/needs-album.mp3",
        TIT2="Township Rebellion", TPE1="Rage Against the Machine",
        TCON="Rock",
    )
    # No Title -> skipped without any request.
    missing_title = _file(
        "/music/missing-title.mp3", TPE1="Rage Against the Machine",
    )
    # Everything requested is empty -> second (and last) request.
    needs_all = _file(
        "/music/needs-all.mp3",
        TIT2="Township Rebellion", TPE1="Rage Against the Machine",
    )
    # Nothing empty -> skipped without any request.
    complete = _file(
        "/music/complete.mp3",
        TIT2="Township Rebellion", TPE1="Rage Against the Machine",
        TALB="Already There", TCON="Rock",
    )

    files = [needs_album, missing_title, needs_all, complete]
    fills, errors = fill_missing(
        files, ["Album", "Genre"],
        opener=opener, sleeper=sleeper,
        progress=lambda done, total, path: progress_calls.append(
            (done, total, path)
        ),
    )

    assert errors == []
    # Only the two files that actually needed a lookup got fills.
    assert fills == {
        "/music/needs-album.mp3": {"Album": "Rage Against the Machine"},
        "/music/needs-all.mp3": {
            "Album": "Rage Against the Machine",
            "Genre": "rap metal",
        },
    }
    # Exactly two requests: the missing-Title and the complete file
    # made NO request.
    assert len(opener.calls) == 2
    requested_urls = [call[0] for call in opener.calls]
    assert all("musicbrainz.org" in url for url in requested_urls)
    # Rate limiting: slept once, before the second request only.
    assert sleeper.calls == [1.0]
    # Progress reported every file, in order.
    assert progress_calls == [
        (1, 4, "/music/needs-album.mp3"),
        (2, 4, "/music/missing-title.mp3"),
        (3, 4, "/music/needs-all.mp3"),
        (4, 4, "/music/complete.mp3"),
    ]


def test_fill_missing_collects_errors_and_continues():
    def failing_opener(url, headers, timeout):
        raise OSError("simulated outage")

    sleeper = FakeSleeper()
    files = [
        _file("/music/a.mp3", TIT2="One", TPE1="Band"),
        _file("/music/b.mp3", TIT2="Two", TPE1="Band"),
    ]
    fills, errors = fill_missing(
        files, ["Album"], opener=failing_opener, sleeper=sleeper,
    )
    assert fills == {}
    assert len(errors) == 2
    assert "/music/a.mp3" in errors[0]
    assert "/music/b.mp3" in errors[1]
    # The second file was still attempted (after one rate-limit sleep).
    assert sleeper.calls == [1.0]


# ---------------------------------------------------------------------------
# Cover art
# ---------------------------------------------------------------------------

def test_cover_tag_name_constant():
    assert COVER_TAG_NAME == "Cover Art"


def test_make_cover_frame_png(tmp_path):
    image = tmp_path / "front.png"
    image.write_bytes(PNG_BYTES)
    frame = make_cover_frame(str(image))
    assert frame.mime == "image/png"
    assert frame.type == 3  # front cover
    assert frame.encoding == 3
    assert frame.desc == ""
    assert bytes(frame.data) == PNG_BYTES  # data round-trips


def test_make_cover_frame_jpeg_mime(tmp_path):
    image = tmp_path / "front.jpg"
    image.write_bytes(b"\xff\xd8\xff fake jpeg bytes")
    frame = make_cover_frame(str(image))
    assert frame.mime == "image/jpeg"


def test_mime_for_image():
    assert mime_for_image("cover.jpg") == "image/jpeg"
    assert mime_for_image("cover.JPEG") == "image/jpeg"
    assert mime_for_image("cover.png") == "image/png"
    with pytest.raises(ValueError) as excinfo:
        mime_for_image("cover.gif")
    # The error lists the supported types.
    assert ".jpg" in str(excinfo.value)
    assert ".png" in str(excinfo.value)


def test_resolve_image_path(tmp_path):
    image = tmp_path / "art" / "front.png"
    image.parent.mkdir()
    image.write_bytes(PNG_BYTES)
    # Relative values resolve against csv_dir.
    resolved = resolve_image_path(
        os.path.join("art", "front.png"), csv_dir=str(tmp_path)
    )
    assert resolved == os.path.abspath(str(image))
    # Absolute values are used as-is.
    assert resolve_image_path(str(image)) == os.path.abspath(str(image))
    with pytest.raises(FileNotFoundError):
        resolve_image_path("nope.png", csv_dir=str(tmp_path))


def test_cover_display():
    assert cover_display("") == "[remove cover art]"
    assert cover_display("   ") == "[remove cover art]"
    assert cover_display(None) == "[remove cover art]"
    assert cover_display("/some/folder/front.png") == "[cover image: front.png]"
    assert cover_display("front.jpg") == "[cover image: front.jpg]"
