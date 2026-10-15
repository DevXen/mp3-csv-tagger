"""Tests for filename/path tag capture and the read-only library report.

The modules under test are pure: :mod:`mp3csvtagger.filename_tags` works
on strings alone and :mod:`mp3csvtagger.library_report` works on
already-scanned :class:`~mp3csvtagger.mp3files.Mp3File` objects, so the
files here are constructed directly and never touch the disk.
"""

from __future__ import annotations

import os

import pytest

from mp3csvtagger.filename_tags import capture, capture_for_file, parse_pattern
from mp3csvtagger.library_report import (
    duplicate_groups,
    render_csv_report,
    render_text_report,
    variant_groups,
)
from mp3csvtagger.mp3files import Mp3File


# ---------------------------------------------------------------------------
# parse_pattern
# ---------------------------------------------------------------------------


def test_parse_pattern_tokens():
    assert parse_pattern("{Lead Performer} - {Title}") == [
        ("tag", "Lead Performer"),
        ("lit", " - "),
        ("tag", "Title"),
    ]
    assert parse_pattern("{Title}") == [("tag", "Title")]
    assert parse_pattern("Track {Track Number}: {Title}") == [
        ("lit", "Track "),
        ("tag", "Track Number"),
        ("lit", ": "),
        ("tag", "Title"),
    ]


@pytest.mark.parametrize(
    "pattern",
    [
        "{}",  # empty tag
        "{ }",  # whitespace-only tag
        "{Title",  # unclosed brace
        "{Lead Performer} - {Title",  # unclosed brace after a valid tag
        "just literal text",  # no tag tokens at all
        "",  # empty pattern: no tag tokens
        "{Title}{Lead Performer}",  # adjacent tags, no literal between
    ],
)
def test_parse_pattern_errors_raise(pattern):
    with pytest.raises(ValueError):
        parse_pattern(pattern)


def test_capture_with_bad_pattern_raises():
    with pytest.raises(ValueError):
        capture("{Title}{Lead Performer}", "anything")


# ---------------------------------------------------------------------------
# capture / capture_for_file
# ---------------------------------------------------------------------------


def test_capture_artist_dash_title():
    assert capture(
        "{Lead Performer} - {Title}",
        "Rage Against the Machine - Township Rebellion",
    ) == {
        "Lead Performer": "Rage Against the Machine",
        "Title": "Township Rebellion",
    }


def test_capture_is_lazy_up_to_the_next_literal():
    # The performer stops at the FIRST " - "; the rest belongs to the title.
    assert capture("{Lead Performer} - {Title}", "A - B - C") == {
        "Lead Performer": "A",
        "Title": "B - C",
    }


def test_capture_leading_and_trailing_tags():
    assert capture("{Title} (live)", "Township Rebellion (live)") == {
        "Title": "Township Rebellion"
    }
    assert capture("Song: {Title}", "Song: Township Rebellion") == {
        "Title": "Township Rebellion"
    }


def test_capture_strips_values_and_rejects_empty_captures():
    assert capture("{Title}!", "  Padded Title  !") == {"Title": "Padded Title"}
    assert capture("{Lead Performer} - {Title}", " - Township Rebellion") is None


def test_capture_non_matching_text_returns_none():
    assert capture("{Lead Performer} - {Title}", "No Delimiter Here") is None
    assert capture("{Lead Performer} - {Title}", "A - B extra - C - D") is not None
    # Anchored: a literal prefix must be present from the very start.
    assert capture("Track {Track Number}: {Title}", "XTrack 1: Song") is None


def test_capture_for_file_uses_filename_stem_by_default():
    path = os.path.join(
        "music", "Rage Against the Machine - Township Rebellion.mp3"
    )
    assert capture_for_file("{Lead Performer} - {Title}", path) == {
        "Lead Performer": "Rage Against the Machine",
        "Title": "Township Rebellion",
    }


def test_capture_for_file_non_matching_name_returns_none():
    path = os.path.join("music", "untitled recording.mp3")
    assert capture_for_file("{Lead Performer} - {Title}", path) is None


def test_capture_for_file_with_path_and_root():
    root = os.path.join("music", "library")
    path = os.path.join(
        root,
        "Rage Against the Machine",
        "Rage Against the Machine",
        "01 - Township Rebellion.mp3",
    )
    assert capture_for_file(
        "{Lead Performer}/{Album}/{Track Number} - {Title}",
        path,
        root=root,
        use_path=True,
    ) == {
        "Lead Performer": "Rage Against the Machine",
        "Album": "Rage Against the Machine",
        "Track Number": "01",
        "Title": "Township Rebellion",
    }


def test_capture_for_file_with_path_without_root_uses_full_path():
    path = os.path.join(
        "Rage Against the Machine",
        "Rage Against the Machine",
        "01 - Township Rebellion.mp3",
    )
    assert capture_for_file(
        "{Lead Performer}/{Album}/{Track Number} - {Title}",
        path,
        use_path=True,
    ) == {
        "Lead Performer": "Rage Against the Machine",
        "Album": "Rage Against the Machine",
        "Track Number": "01",
        "Title": "Township Rebellion",
    }


# ---------------------------------------------------------------------------
# duplicate_groups
# ---------------------------------------------------------------------------


def _song(path, title, artist):
    return Mp3File(path=path, tags={"TIT2": title, "TPE1": artist})


def test_duplicate_groups_same_title_and_artist():
    files = [
        _song("/music/a/township.mp3", "Township Rebellion",
              "Rage Against the Machine"),
        _song("/music/b/township copy.mp3", "Township Rebellion",
              "Rage Against the Machine"),
        _song("/music/a/other.mp3", "Something Else", "Another Band"),
    ]
    groups = duplicate_groups(files)
    assert len(groups) == 1
    assert groups[0]["title"] == "Township Rebellion"
    assert groups[0]["artist"] == "Rage Against the Machine"
    assert groups[0]["paths"] == ["/music/a/township.mp3", "/music/b/township copy.mp3"]


def test_duplicate_groups_match_after_normalisation():
    # Case/punctuation differences do not hide a duplicate.
    files = [
        _song("/music/one.mp3", "Township Rebellion", "Rage Against the Machine"),
        _song("/music/two.mp3", "township rebellion!", "rage against the machine"),
    ]
    groups = duplicate_groups(files)
    assert len(groups) == 1
    assert groups[0]["paths"] == ["/music/one.mp3", "/music/two.mp3"]


def test_duplicate_groups_skip_missing_values_and_sort():
    files = [
        _song("/music/z1.mp3", "Zulu Song", "Zed Band"),
        _song("/music/no-title.mp3", "", "Zed Band"),
        _song("/music/no-artist.mp3", "Zulu Song", ""),
        _song("/music/a1.mp3", "Alpha Song", "Alpha Band"),
        _song("/music/z2.mp3", "Zulu Song", "Zed Band"),
        _song("/music/a2.mp3", "Alpha Song", "Alpha Band"),
    ]
    groups = duplicate_groups(files)
    assert [group["artist"] for group in groups] == ["Alpha Band", "Zed Band"]
    assert all(len(group["paths"]) == 2 for group in groups)


def test_duplicate_groups_friendly_tag_names_also_found():
    files = [
        Mp3File(path="/music/one.mp3",
                tags={"Title": "Song", "Lead Performer": "Band"}),
        Mp3File(path="/music/two.mp3",
                tags={"Title": "Song", "Lead Performer": "Band"}),
    ]
    assert len(duplicate_groups(files)) == 1


# ---------------------------------------------------------------------------
# variant_groups
# ---------------------------------------------------------------------------


def test_variant_groups_artist_spellings():
    # "beatles" and "Beatles" normalise alike, so they are variants of one
    # value. "The Beatles" normalises to "the beatles" — a genuinely
    # different value under matching.normalize, so it is NOT in the group.
    files = [
        Mp3File(path="/music/beatles/1.mp3", tags={"TPE1": "The Beatles"}),
        Mp3File(path="/music/beatles/2.mp3", tags={"TPE1": "beatles"}),
        Mp3File(path="/music/beatles/3.mp3", tags={"TPE1": "Beatles"}),
        Mp3File(path="/music/other/1.mp3", tags={"TPE1": "Another Band"}),
        Mp3File(path="/music/blank/1.mp3", tags={"TPE1": ""}),
    ]
    groups = variant_groups(files, "Lead Performer")
    assert len(groups) == 1
    group = groups[0]
    assert group["tag"] == "Lead Performer"
    assert group["normalized"] == "beatles"
    assert group["spellings"] == {
        "beatles": ["/music/beatles/2.mp3"],
        "Beatles": ["/music/beatles/3.mp3"],
    }


def test_variant_groups_case_and_punctuation_spellings():
    files = [
        Mp3File(path="/music/beatles/1.mp3", tags={"TPE1": "The Beatles"}),
        Mp3File(path="/music/beatles/2.mp3", tags={"TPE1": "the beatles"}),
        Mp3File(path="/music/beatles/3.mp3", tags={"TPE1": "THE BEATLES!"}),
    ]
    groups = variant_groups(files, "Lead Performer")
    assert len(groups) == 1
    assert groups[0]["normalized"] == "the beatles"
    assert groups[0]["spellings"] == {
        "The Beatles": ["/music/beatles/1.mp3"],
        "the beatles": ["/music/beatles/2.mp3"],
        "THE BEATLES!": ["/music/beatles/3.mp3"],
    }


def test_variant_groups_by_frame_id_and_no_variants():
    files = [
        Mp3File(path="/music/1.mp3", tags={"TPE1": "Beatles"}),
        Mp3File(path="/music/2.mp3", tags={"TPE1": "Beatles"}),
    ]
    # Same spelling twice is not a variant; frame ids resolve as names too.
    assert variant_groups(files, "TPE1") == []
    assert variant_groups(files, "Genre") == []


# ---------------------------------------------------------------------------
# render_text_report
# ---------------------------------------------------------------------------


def test_render_text_report_sections_counts_and_paths():
    files = [
        _song("/music/a/township.mp3", "Township Rebellion",
              "Rage Against the Machine"),
        _song("/music/b/township copy.mp3", "Township Rebellion",
              "Rage Against the Machine"),
        Mp3File(path="/music/beatles/1.mp3", tags={"TPE1": "Beatles"}),
        Mp3File(path="/music/beatles/2.mp3", tags={"TPE1": "beatles"}),
    ]
    report = render_text_report(
        duplicate_groups(files[:2]),
        [variant_groups(files[2:], "Lead Performer")],
    )
    assert "Duplicates: 1 group(s), 2 file(s)" in report
    assert '"Township Rebellion" by Rage Against the Machine' in report
    assert "    /music/a/township.mp3" in report
    assert "    /music/b/township copy.mp3" in report
    assert "Spelling variants: 1 group(s), 2 spelling(s)" in report
    assert 'Lead Performer: "beatles"' in report
    assert '"Beatles"' in report
    assert '"beatles"' in report
    assert "      /music/beatles/1.mp3" in report


def test_render_text_report_flat_variant_list_and_empty_sections():
    report = render_text_report([], variant_groups([], "Lead Performer"))
    assert "Duplicates: 0 group(s), 0 file(s)" in report
    assert "Spelling variants: 0 group(s), 0 spelling(s)" in report
    assert report.count("(none)") == 2


def test_render_csv_report_one_row_per_file():
    import csv
    import io

    files = [
        _song("/music/a/township.mp3", "Township Rebellion",
              "Rage Against the Machine"),
        _song("/music/b/township copy.mp3", "Township Rebellion",
              "Rage Against the Machine"),
        Mp3File(path="/music/beatles/1.mp3", tags={"TPE1": "Beatles"}),
        Mp3File(path="/music/beatles/2.mp3", tags={"TPE1": "beatles"}),
    ]
    rows = list(csv.reader(io.StringIO(render_csv_report(
        duplicate_groups(files[:2]),
        [variant_groups(files[2:], "Lead Performer")],
    ))))
    assert rows[0] == ["Kind", "Tag", "Title", "Artist", "Normalized",
                       "Spelling", "File"]
    assert rows[1] == ["duplicate", "", "Township Rebellion",
                       "Rage Against the Machine", "", "",
                       "/music/a/township.mp3"]
    assert rows[2][0] == "duplicate" and rows[2][6] == "/music/b/township copy.mp3"
    variant_rows = [r for r in rows[1:] if r[0] == "variant"]
    assert len(variant_rows) == 2
    assert {r[5] for r in variant_rows} == {"Beatles", "beatles"}
    assert all(r[1] == "Lead Performer" and r[4] == "beatles"
               for r in variant_rows)
