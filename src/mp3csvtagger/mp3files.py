"""Scanning MP3 files and reading their tags, in parallel.

Scanning is designed to stay fast and to never die on one bad file:

* folders are walked once and their paths collected first (cheap),
* tags are read with a thread pool — several times faster than reading
  serially on real libraries,
* "no ID3 header" and "unreadable file" are treated as data, not as a
  crash: the file simply starts with no tags (applying creates the header).
"""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from mutagen.id3 import ID3

from .tags import tag_name_and_value


@dataclass
class Mp3File:
    """One MP3 file and the editable text tags currently stored in it."""

    path: str
    #: Tag name -> current value. For standard frames the name is the frame
    #: id (``TIT2``); for custom ``TXXX`` frames it is the description.
    tags: dict[str, str] = field(default_factory=dict)
    #: Set when the file could not be read at all.
    error: str | None = None
    #: True when the file carries embedded cover art (an APIC frame). The
    #: image bytes are deliberately NOT loaded during a scan — they are
    #: large, and tagging decisions only need to know art is present.
    has_cover: bool = False

    @property
    def filename(self) -> str:
        """Base name of the file."""
        return os.path.basename(self.path)

    def value_for(self, tag_name: str, frame: str) -> str:
        """Current value for a CSV column, by friendly name or frame id."""
        if tag_name in self.tags:
            return self.tags[tag_name]
        return self.tags.get(frame, "")


def read_tags(path: str) -> Mp3File:
    """Read one file's tags; never raises for a missing/corrupt header."""
    result = Mp3File(path=path)
    try:
        audio = ID3(path)
    except Exception as exc:  # no header (ID3NoHeaderError) or unreadable file
        # A file with no header simply has no tags yet. Any other mutagen
        # error is reported on the file so the GUI/CLI can show it.
        if exc.__class__.__name__ == "ID3NoHeaderError":
            return result
        result.error = f"{exc.__class__.__name__}: {exc}"
        return result
    if audio is None:
        return result
    for frame in audio.values():
        if getattr(frame, "FrameID", "") == "APIC":
            result.has_cover = True
            continue  # image data is not a text tag; see has_cover above
        pair = tag_name_and_value(frame)
        if pair is None:
            continue
        name, value = pair
        if name:
            result.tags[name] = value
    return result


def collect_mp3_paths(paths: list[str]) -> list[str]:
    """Expand files/folders into a sorted, de-duplicated list of MP3 paths."""
    found: list[str] = []
    seen: set[str] = set()
    for raw in paths:
        path = raw.replace("/", os.sep)
        if os.path.isfile(path):
            candidates = [path]
        elif os.path.isdir(path):
            candidates = []
            for dir_name, _sub_dirs, files in os.walk(path):
                for fname in sorted(files):
                    if fname.lower().endswith(".mp3"):
                        candidates.append(os.path.join(dir_name, fname))
        else:
            continue
        for candidate in candidates:
            key = os.path.normcase(os.path.abspath(candidate))
            if key not in seen:
                seen.add(key)
                found.append(candidate)
    return found


def scan(
    paths: list[str],
    *,
    workers: int | None = None,
    progress=None,
) -> list[Mp3File]:
    """Scan *paths* (files and/or folders) and read every MP3's tags.

    ``progress(done, total, path)`` is called as files complete, if given.
    ``workers`` defaults to a pool sized for disk-bound tag reading.
    """
    file_paths = collect_mp3_paths(paths)
    if not file_paths:
        return []
    if workers is None:
        workers = min(32, max(4, (os.cpu_count() or 4) * 2))
    results: list[Mp3File] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for done, mp3 in enumerate(pool.map(read_tags, file_paths), start=1):
            results.append(mp3)
            if progress is not None:
                progress(done, len(file_paths), mp3.path)
    # pool.map preserves input order, so results line up with the sorted walk.
    return results
