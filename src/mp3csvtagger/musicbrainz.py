"""Opt-in MusicBrainz lookup that fills EMPTY tags only.

This module is deliberately separate from the core tagging engine: nothing
here runs unless the caller explicitly asks for a lookup, and a lookup never
overwrites a value a file already has.  It can suggest an album, a recording
date / year and a genre for a track whose artist (Lead Performer, ``TPE1``)
and title (``TIT2``) are already known.

Network access is injected through an ``opener`` callable so the whole
module is testable offline::

    opener(url, headers, timeout) -> bytes

The default opener is a small :mod:`urllib.request` implementation.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

from .mp3files import Mp3File
from .tags import frame_for_tag_name

#: User-Agent sent with every MusicBrainz request.  MusicBrainz asks
#: applications to identify themselves (including a contact / project URL).
USER_AGENT = "MP3CsvTagger/1.3.0 ( https://github.com/DevXen/mp3-csv-tagger )"

#: Base URL of the MusicBrainz web service (version 2).
BASE = "https://musicbrainz.org/ws/2"

__all__ = [
    "BASE",
    "USER_AGENT",
    "LookupError",
    "search_recording",
    "fields_from_recording",
    "fill_missing",
]


class LookupError(RuntimeError):
    """Raised when a MusicBrainz lookup fails.

    Subclasses :class:`RuntimeError` (rather than the built-in
    ``LookupError``) so callers can distinguish a failed remote lookup from
    an ordinary missing-key error in their own data.
    """


def _default_opener(url: str, headers: dict, timeout: float) -> bytes:
    """Fetch *url* with :mod:`urllib.request` and return the body bytes.

    This is the default ``opener`` for :func:`search_recording`; tests and
    other callers can supply their own callable with the same signature.
    """
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def _escape_query_value(value: str) -> str:
    """Escape a value for inclusion inside double quotes in a query.

    Embedded double quotes are backslash-escaped so a title such as
    ``Say "Hello"`` cannot break out of its quoted query term.
    """
    return str(value).replace('"', '\\"')


def search_recording(artist, title, *, opener=None, timeout=20):
    """Search MusicBrainz for a recording by *artist* and *title*.

    Performs ``GET {BASE}/recording/?query=recording:"<title>" AND
    artist:"<artist>"&fmt=json`` with the :data:`USER_AGENT` header.
    Embedded double quotes in *artist* / *title* are escaped.

    Args:
        artist: The performing artist to search for.
        title: The recording title to search for.
        opener: Optional callable ``opener(url, headers, timeout) -> bytes``.
            Defaults to a :mod:`urllib.request` implementation.
        timeout: Timeout (in seconds) passed through to *opener*.

    Returns:
        The first item of the response's ``"recordings"`` list as a dict,
        or ``None`` when MusicBrainz returned no recordings.

    Raises:
        LookupError: On any HTTP, network or JSON-parse failure, with a
            message describing what failed.
    """
    if opener is None:
        opener = _default_opener
    query = (
        f'recording:"{_escape_query_value(title)}"'
        f' AND artist:"{_escape_query_value(artist)}"'
    )
    url = f"{BASE}/recording/?query={query}&fmt=json"
    headers = {"User-Agent": USER_AGENT}
    try:
        body = opener(url, headers, timeout)
    except LookupError:
        raise
    except Exception as exc:  # HTTP error, network error, timeout, ...
        raise LookupError(
            f"MusicBrainz recording search failed for "
            f"artist={artist!r} title={title!r}: {exc}"
        ) from exc
    try:
        data = json.loads(body)
    except Exception as exc:
        raise LookupError(
            f"MusicBrainz recording search returned unparseable data for "
            f"artist={artist!r} title={title!r}: {exc}"
        ) from exc
    if not isinstance(data, dict):
        raise LookupError(
            f"MusicBrainz recording search returned unexpected data for "
            f"artist={artist!r} title={title!r}: expected a JSON object"
        )
    recordings = data.get("recordings") or []
    if not recordings:
        return None
    return recordings[0]


def _first_release(recording: dict) -> dict:
    """Return the first entry of a recording's ``"releases"`` list, or ``{}``."""
    releases = recording.get("releases") or []
    if releases and isinstance(releases[0], dict):
        return releases[0]
    return {}


def _recording_date(recording: dict) -> str:
    """Return the best recording date: first-release-date, else release date."""
    date = recording.get("first-release-date")
    if date:
        return str(date)
    release_date = _first_release(recording).get("date")
    return str(release_date) if release_date else ""


def fields_from_recording(recording, wanted) -> dict[str, str]:
    """Extract supported tag fields from a MusicBrainz *recording* dict.

    Exactly these fields are supported:

    * ``"Album"`` — ``releases[0]["title"]``, if present.
    * ``"Recording Date"`` — ``recording["first-release-date"]``, falling
      back to ``releases[0]["date"]``.
    * ``"Year"`` — the first 4 characters of that same date.
    * ``"Genre"`` — the ``name`` of the highest-``count`` entry in
      ``recording["tags"]``.

    Args:
        recording: One recording dict, as returned by
            :func:`search_recording`.  ``None`` yields an empty dict.
        wanted: Iterable of field names the caller is interested in.

    Returns:
        A dict of ``{field: value}`` containing only fields that are both
        in *wanted* and have a non-empty value in *recording*.  Unsupported
        names in *wanted* are ignored.
    """
    if not recording:
        return {}
    wanted_set = set(wanted or [])
    result: dict[str, str] = {}

    date = _recording_date(recording)

    if "Album" in wanted_set:
        album = _first_release(recording).get("title")
        if album:
            result["Album"] = str(album)
    if "Recording Date" in wanted_set:
        if date:
            result["Recording Date"] = date
    if "Year" in wanted_set:
        if date:
            result["Year"] = date[:4]
    if "Genre" in wanted_set:
        tags = recording.get("tags") or []
        best_name = ""
        best_count = None
        for tag in tags:
            if not isinstance(tag, dict):
                continue
            name = tag.get("name")
            if not name:
                continue
            try:
                count = int(tag.get("count") or 0)
            except (TypeError, ValueError):
                count = 0
            if best_count is None or count > best_count:
                best_count = count
                best_name = str(name)
        if best_name:
            result["Genre"] = best_name
    # Preserve the caller's `wanted` ordering where possible.
    ordered: dict[str, str] = {}
    for field in wanted or []:
        if field in result and field not in ordered:
            ordered[field] = result[field]
    for field, value in result.items():
        ordered.setdefault(field, value)
    return ordered


def fill_missing(files, fields, *, opener=None, sleeper=time.sleep,
                 min_interval=1.0, progress=None):
    """Fill empty tags on *files* from MusicBrainz, one search per file.

    For each :class:`~mp3csvtagger.mp3files.Mp3File` that has a non-empty
    Title (``TIT2``) and Lead Performer (``TPE1``), the fields in *fields*
    that are currently empty (checked via
    :meth:`Mp3File.value_for`) are looked up.  Files missing a title or a
    lead performer, and files where none of *fields* are empty, are skipped
    without making any request.  Values a file already has are never
    overwritten — only still-empty fields are kept from each result.

    Args:
        files: Iterable of :class:`Mp3File` objects to consider.
        fields: Tag field names to try to fill, e.g.
            ``["Album", "Year", "Genre"]``.
        opener: Optional callable passed through to
            :func:`search_recording`.
        sleeper: Callable used to wait between requests; defaults to
            :func:`time.sleep`.  Tests can inject a recording fake.
        min_interval: Seconds to pass to *sleeper* before each request
            after the first.
        progress: Optional callable ``progress(done, total, path)`` called
            as each file is processed.

    Returns:
        A tuple ``(fills, errors)`` where *fills* is
        ``{path: {field: value}}`` for every file that gained at least one
        value, and *errors* is a list of human-readable strings, one per
        file whose lookup failed.  A single file's failure never stops the
        remaining files.
    """
    files = list(files)
    fields = list(fields or [])
    fills: dict[str, dict[str, str]] = {}
    errors: list[str] = []
    total = len(files)
    requests_made = 0

    for done, mp3 in enumerate(files, start=1):
        try:
            title = mp3.value_for("Title", "TIT2")
            artist = mp3.value_for("Lead Performer", "TPE1")
            if title and title.strip() and artist and artist.strip():
                empty_fields = [
                    field for field in fields
                    if not (
                        mp3.value_for(field, frame_for_tag_name(field)) or ""
                    ).strip()
                ]
                if empty_fields:
                    if requests_made:
                        # MusicBrainz rate limit: max 1 req/s — wait
                        # before every request except the first.
                        sleeper(min_interval)
                    requests_made += 1
                    try:
                        recording = search_recording(
                            artist, title, opener=opener
                        )
                    except Exception as exc:
                        errors.append(f"{mp3.path}: {exc}")
                    else:
                        if recording is not None:
                            found = fields_from_recording(
                                recording, empty_fields
                            )
                            # Keep only the still-empty fields (paranoia:
                            # fields_from_recording was already asked only
                            # for those, but never fill a non-empty tag).
                            found = {
                                field: value
                                for field, value in found.items()
                                if field in empty_fields and value
                            }
                            if found:
                                fills[mp3.path] = found
        finally:
            if progress is not None:
                progress(done, total, mp3.path)
    return fills, errors
