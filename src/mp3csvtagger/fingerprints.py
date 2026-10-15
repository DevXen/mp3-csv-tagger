"""Chromaprint fingerprints and AcoustID lookups.

A *fingerprint* identifies a recording by its audio, not its tags or
its file name. That makes fingerprints the fallback for the two jobs
tags cannot do:

* pairing two copies of a library whose files do not line up by path
  (see :func:`mp3csvtagger.sync.pair_leftovers_by_fingerprint`), and
* spotting files in one library that are the same recording wearing
  different tags (:func:`same_recording_groups`).

Fingerprints are computed by the external ``fpcalc`` tool from the
Chromaprint project — it is not bundled, and this module degrades
quietly when it is absent: :func:`fingerprint_file` simply returns
``None``. Results are cached on disk (keyed by absolute path, guarded
by file size + mtime) because running ``fpcalc`` over a whole library
is the slow part and tags change far more often than audio does.

:func:`acoustid_lookup` asks the AcoustID web service what recording a
fingerprint belongs to. It is strictly opt-in: it needs the user's own
API key (stored in the settings file, see :func:`acoustid_api_key`),
it raises before touching the network when no key is set, and it
spaces its calls at least a second apart, as the service asks.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

#: Environment variables that override the on-disk locations. They
#: follow the same pattern as the presets directory (see
#: :mod:`mp3csvtagger.presets`): the variable names a *directory* and
#: the file lives inside it. Tests use them to keep state in a temp
#: folder; portable installs can use them to carry state along.
CACHE_DIR_ENV_VAR = "MP3CSVTAGGER_CACHE_DIR"
SETTINGS_DIR_ENV_VAR = "MP3CSVTAGGER_SETTINGS_DIR"

#: AcoustID lookup endpoint and the minimum spacing between calls.
#: AcoustID asks API users to make at most about three calls a second;
#: one second is comfortably inside that and keeps a library-sized run
#: polite.
ACOUSTID_LOOKUP_URL = "https://api.acoustid.org/v2/lookup"
MIN_LOOKUP_SPACING_SECONDS = 1.0

#: Monotonic timestamp of the last AcoustID call this process made.
#: Module state on purpose: the spacing rule is about the process's
#: traffic to the service, not about one call site.
_last_lookup_at: float | None = None


@dataclass
class Fingerprint:
    """One file's Chromaprint fingerprint and its audio duration."""

    duration: float
    fingerprint: str


# ---------------------------------------------------------------------------
# fpcalc
# ---------------------------------------------------------------------------

def fpcalc_path() -> str | None:
    """The path of the ``fpcalc`` executable, or ``None`` if not installed."""
    return shutil.which("fpcalc")


def _state_dir(env_var: str) -> Path:
    """Directory for a state file: the env override, else ~/.mp3csvtagger/.

    Mirrors :func:`mp3csvtagger.presets.presets_dir`: an environment
    variable names the directory when set and non-empty, otherwise the
    directory is the user's ``.mp3csvtagger`` folder. The directory
    (including parents) is created on demand.
    """
    override = os.environ.get(env_var)
    if override:
        directory = Path(override).expanduser()
    else:
        directory = Path.home() / ".mp3csvtagger"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def cache_path() -> Path:
    """Path of the fingerprint cache file, creating its directory.

    ``$MP3CSVTAGGER_CACHE_DIR/fingerprint-cache.json`` when that
    environment variable is set, otherwise
    ``~/.mp3csvtagger/fingerprint-cache.json``.
    """
    return _state_dir(CACHE_DIR_ENV_VAR) / "fingerprint-cache.json"


def _load_cache() -> dict:
    """Read the fingerprint cache; a missing/corrupt cache reads as empty.

    A corrupt cache must never break fingerprinting — the worst case
    is recomputing, which is exactly what an empty cache means.
    """
    try:
        with open(cache_path(), encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _save_cache(cache: dict) -> None:
    """Write the fingerprint cache, best-effort.

    Failing to cache (read-only home, full disk) must not fail the
    fingerprint itself, so write errors are swallowed here — the next
    run simply recomputes.
    """
    try:
        with open(cache_path(), "w", encoding="utf-8") as handle:
            json.dump(cache, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
    except OSError:
        pass


def fingerprint_file(path, *, use_cache=True, runner=None) -> Fingerprint | None:
    """Fingerprint one file with ``fpcalc``; ``None`` when unavailable.

    *runner* defaults to :func:`subprocess.run` and is invoked as
    ``runner([fpcalc, "-json", path], capture_output=True, text=True)``;
    its stdout is parsed as the JSON ``fpcalc -json`` prints,
    ``{"duration": float, "fingerprint": str}``. Tests inject a fake
    runner, so no test needs a real ``fpcalc``.

    Returns ``None`` — never raises — when ``fpcalc`` is not installed,
    the file cannot be statted, the call fails, or its output does not
    parse: a missing fingerprint is data (the file just will not pair
    by fingerprint), not an error worth stopping a library scan for.

    With *use_cache* (the default), a cache entry whose recorded size
    and mtime still match the file is returned without calling
    ``fpcalc`` at all; a stale entry (the file changed) is recomputed
    and the cache updated.
    """
    absolute = os.path.abspath(str(path))
    try:
        stat = os.stat(absolute)
    except OSError:
        return None
    size, mtime = int(stat.st_size), int(stat.st_mtime)

    cache = _load_cache() if use_cache else {}
    if use_cache:
        entry = cache.get(absolute)
        if (
            isinstance(entry, dict)
            and entry.get("size") == size
            and entry.get("mtime") == mtime
            and entry.get("fingerprint")
        ):
            return Fingerprint(
                duration=float(entry.get("duration") or 0.0),
                fingerprint=str(entry["fingerprint"]),
            )

    fpcalc = fpcalc_path()
    if fpcalc is None:
        return None
    if runner is None:
        runner = subprocess.run
    try:
        result = runner([fpcalc, "-json", absolute], capture_output=True, text=True)
    except Exception:
        return None
    if getattr(result, "returncode", 0) not in (0, None):
        return None
    try:
        payload = json.loads(getattr(result, "stdout", "") or "")
        fingerprint = Fingerprint(
            duration=float(payload["duration"]),
            fingerprint=str(payload["fingerprint"]),
        )
    except (ValueError, KeyError, TypeError):
        return None
    if not fingerprint.fingerprint:
        return None

    if use_cache:
        cache[absolute] = {
            "size": size,
            "mtime": mtime,
            "duration": fingerprint.duration,
            "fingerprint": fingerprint.fingerprint,
        }
        _save_cache(cache)
    return fingerprint


def fingerprints_for(files, *, progress=None) -> dict[str, Fingerprint]:
    """Fingerprint every file in *files*; return ``{path: Fingerprint}``.

    *files* may hold path strings or scanned
    :class:`~mp3csvtagger.mp3files.Mp3File` objects (their ``.path`` is
    used). Files that cannot be fingerprinted (no ``fpcalc``, unreadable
    audio) are simply absent from the result. ``progress(done, total,
    path)`` is called per file, if given.
    """
    paths = [str(getattr(item, "path", item)) for item in files]
    results: dict[str, Fingerprint] = {}
    for done, path in enumerate(paths, start=1):
        fingerprint = fingerprint_file(path)
        if fingerprint is not None:
            results[path] = fingerprint
        if progress is not None:
            progress(done, len(paths), path)
    return results


def same_recording_groups(files, fps) -> list[dict]:
    """Group scanned *files* that share a fingerprint but differ in tags.

    *fps* is a ``{path: Fingerprint}`` mapping as returned by
    :func:`fingerprints_for`. Files are grouped by fingerprint string;
    a group is returned only when it has at least two files **and**
    their tag dicts are not all identical — a group whose tags already
    agree completely is the same recording in the same state, which is
    not a finding worth reporting. Each group is
    ``{"fingerprint": ..., "duration": ..., "paths": [...]}`` with the
    duration taken from the first file's fingerprint and paths in the
    order *files* were given.
    """
    fps = fps or {}
    by_fingerprint: dict[str, list] = {}
    for mp3 in files:
        fingerprint = fps.get(mp3.path)
        if fingerprint is None:
            continue
        by_fingerprint.setdefault(fingerprint.fingerprint, []).append(mp3)

    groups: list[dict] = []
    for fingerprint_text, members in by_fingerprint.items():
        if len(members) < 2:
            continue
        first_tags = dict(members[0].tags)
        if all(dict(member.tags) == first_tags for member in members[1:]):
            continue  # same recording AND same tags: nothing to reconcile
        groups.append(
            {
                "fingerprint": fingerprint_text,
                "duration": fps[members[0].path].duration,
                "paths": [member.path for member in members],
            }
        )
    return groups


# ---------------------------------------------------------------------------
# Settings (the user's own AcoustID API key lives here)
# ---------------------------------------------------------------------------

def settings_path() -> Path:
    """Path of the settings file, creating its directory.

    ``$MP3CSVTAGGER_SETTINGS_DIR/settings.json`` when that environment
    variable is set, otherwise ``~/.mp3csvtagger/settings.json``.
    """
    return _state_dir(SETTINGS_DIR_ENV_VAR) / "settings.json"


def load_settings() -> dict:
    """Read the settings file; missing/corrupt settings read as ``{}``."""
    try:
        with open(settings_path(), encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def save_settings(settings: dict) -> Path:
    """Write *settings* to the settings file and return its path."""
    path = settings_path()
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(dict(settings), handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    return path


def acoustid_api_key() -> str:
    """The user's AcoustID API key from settings ("" when not set)."""
    return str(load_settings().get("acoustid_api_key") or "")


# ---------------------------------------------------------------------------
# AcoustID lookup
# ---------------------------------------------------------------------------

def _release_year(releasegroup: dict) -> int | None:
    """Best-effort release year from an AcoustID release-group dict.

    AcoustID reports first-release dates in a few shapes — a dict with
    a ``year`` member, or a ``"YYYY..."`` string — under either a
    ``firstreleasedate`` or ``first_releasedate`` key. Anything
    unrecognised yields ``None`` rather than a guessed year.
    """
    for key in ("firstreleasedate", "first_releasedate"):
        value = releasegroup.get(key)
        if isinstance(value, dict) and value.get("year"):
            try:
                return int(value["year"])
            except (TypeError, ValueError):
                return None
        if isinstance(value, str) and value[:4].isdigit():
            return int(value[:4])
        if isinstance(value, int):
            return value
    return None


def acoustid_lookup(fp, api_key, *, opener=None, sleeper=None) -> list[dict]:
    """Look a fingerprint up on AcoustID; return recording matches.

    *fp* is a :class:`Fingerprint`; *api_key* is the user's own
    AcoustID API key. A GET is made to the AcoustID lookup endpoint with
    ``meta=recordings+releasegroups+compress`` so each match carries
    its title, artist, album and year in one response.

    Returns one ``{"score", "title", "artist", "album", "year"}`` dict
    per recording found, sorted by score descending (``year`` is
    ``None`` when AcoustID gives no usable release date).

    Calls from this process are spaced at least
    :data:`MIN_LOOKUP_SPACING_SECONDS` apart: the wait before a call is
    computed from the previous call's monotonic timestamp and slept off
    with *sleeper* (default :func:`time.sleep`).

    *opener* defaults to :func:`urllib.request.urlopen` and is called
    with the full URL; it must return a response whose ``read()`` gives
    the response body (a context manager is used when offered). Tests
    inject a fake opener, so no test makes a live call.

    Raises:
        ValueError: If *api_key* is empty — raised **before** any
            network traffic, because a keyless lookup can only fail and
            the user needs to know the fix is "add your key", not a
            network error.
    """
    global _last_lookup_at
    if not api_key or not str(api_key).strip():
        raise ValueError(
            "An AcoustID API key is required for lookups: add your own "
            "key in settings (acoustid_api_key) and try again."
        )
    if opener is None:
        opener = urllib.request.urlopen
    if sleeper is None:
        sleeper = time.sleep

    # Spacing: sleep off whatever is left of the minimum gap since the
    # previous call from this process, then stamp this call.
    now = time.monotonic()
    if _last_lookup_at is not None:
        remaining = MIN_LOOKUP_SPACING_SECONDS - (now - _last_lookup_at)
        if remaining > 0:
            sleeper(remaining)
    _last_lookup_at = time.monotonic()

    query = urllib.parse.urlencode(
        {
            "client": str(api_key),
            "duration": int(fp.duration),
            "fingerprint": fp.fingerprint,
            "meta": "recordings+releasegroups+compress",
        }
    )
    url = f"{ACOUSTID_LOOKUP_URL}?{query}"
    response = opener(url)
    if hasattr(response, "__enter__") and hasattr(response, "__exit__"):
        with response as handle:
            body = handle.read()
    else:
        body = response.read()
    if isinstance(body, bytes):
        body = body.decode("utf-8", errors="replace")
    payload = json.loads(body)

    matches: list[dict] = []
    for result in payload.get("results") or []:
        try:
            score = float(result.get("score") or 0.0)
        except (TypeError, ValueError):
            score = 0.0
        recordings = result.get("recordings") or []
        if not recordings:
            continue
        for recording in recordings:
            artists = recording.get("artists") or []
            artist_names = [
                str(artist.get("name", "")) if isinstance(artist, dict) else str(artist)
                for artist in artists
            ]
            releasegroups = recording.get("releasegroups") or []
            album, year = "", None
            if releasegroups:
                album = str(releasegroups[0].get("title", "") or "")
                year = _release_year(releasegroups[0])
            matches.append(
                {
                    "score": score,
                    "title": str(recording.get("title", "") or ""),
                    "artist": ", ".join(name for name in artist_names if name),
                    "album": album,
                    "year": year,
                }
            )
    matches.sort(key=lambda match: match["score"], reverse=True)
    return matches
