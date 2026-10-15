"""Tag-snapshot undo: put a file's tags back without copying its audio.

Design
------
A normal tag write changes only a few hundred bytes at the start of an
MP3, while the audio itself is megabytes.  Copying the whole file just to
be able to undo a tag edit would be slow, wasteful, and — for a library of
thousands of files — huge.  So undo here never copies audio at all: before
tags are changed, the caller snapshots just the *frames* of the ID3 tag
(see :func:`make_entry`), and an undo file stores one snapshot per file.

A snapshot is a list of frames, each serialised with :mod:`pickle` and
base64-encoded so the whole undo file can be plain JSON (gzip-compressed,
because snapshots for a big run still add up and JSON compresses well).
Pickling the real mutagen frame objects — rather than re-encoding each
frame type by hand — means every frame type, known or custom (``TXXX``
included), round-trips exactly, with no per-type conversion table to keep
in sync with mutagen.

Two kinds of frame are treated specially:

* ``APIC`` (cover art) is excluded by default.  A cover image can be
  larger than every other frame in the file combined, and normal tag
  writes never touch it, so snapshotting it for every file would bloat
  every undo file to protect against a change that never happens.  A
  caller that *is* about to change a cover passes ``include_apic=True``;
  that flag is recorded in the entry so restore knows whether the
  snapshot owns the cover (replace it) or not (leave the live one alone).
* ``PRIV`` (private frames) is always skipped, even with
  ``include_apic=True``.  This program never writes private frames, they
  can hold owner-specific binary data, and undo has no business
  resurrecting or deleting another tool's private state.

Safety guard
------------
Every entry records the file's size and modification time when the
snapshot was taken.  A snapshot is only meaningful for the exact file it
was taken from: if the file on disk has a different size or mtime at
restore time, something else has changed it since (a re-rip, a replace,
another editor), and blindly writing the old frames onto it could put
tags from one file onto another.  Such a file is *skipped* unless the
caller passes ``force=True`` to say "I know, do it anyway".  The guard
is deliberately cheap — two ``stat`` numbers, no hashing of megabytes of
audio just to undo a title change.
"""

from __future__ import annotations

import base64
import gzip
import json
import os
import pickle
from dataclasses import dataclass, field
from datetime import datetime, timezone

from mutagen.id3 import ID3, ID3NoHeaderError
from mutagen.id3 import delete as _id3_delete

#: Value of the ``"format"`` key that identifies one of our undo files.
UNDO_FORMAT = "mp3csvtagger-undo"

#: Undo-file format version written by :func:`write_undo_file`.
UNDO_VERSION = 1

__all__ = [
    "UNDO_FORMAT",
    "UNDO_VERSION",
    "UndoResult",
    "snapshot_frames",
    "make_entry",
    "write_undo_file",
    "read_undo_file",
    "restore_entry",
    "undo_run",
]


def snapshot_frames(audio, include_apic: bool = False) -> list[dict]:
    """Serialise every frame in a mutagen ``ID3`` object.

    Args:
        audio: An open ``mutagen.id3.ID3`` object.
        include_apic: Also snapshot ``APIC`` (cover art) frames.  Off by
            default because covers are big and normal tag writes never
            touch them — see the module docstring.

    Returns:
        A list of ``{"key": frame.HashKey, "data": <base64 str>}`` dicts,
        one per frame, in tag order.  ``APIC`` frames are skipped unless
        *include_apic* is true; ``PRIV`` frames are always skipped.
    """
    frames: list[dict] = []
    for frame in audio.values():
        frame_id = getattr(frame, "FrameID", "")
        if frame_id == "PRIV":
            # Never snapshotted: we never write PRIV, and restore must
            # never delete or resurrect another tool's private frames.
            continue
        if frame_id == "APIC" and not include_apic:
            # Covers are excluded by default because they are big and
            # untouched by normal writes; see the module docstring.
            continue
        frames.append(
            {
                "key": frame.HashKey,
                # Pickle the real frame object so every frame type —
                # including custom TXXX frames — round-trips exactly.
                # Base64 makes the binary pickle safe to store as JSON.
                "data": base64.b64encode(pickle.dumps(frame)).decode("ascii"),
            }
        )
    return frames


def make_entry(path, include_apic: bool = False) -> dict:
    """Snapshot one file's tags into an undo entry dict.

    Args:
        path: Path to the MP3 file.
        include_apic: Also snapshot ``APIC`` (cover art) frames; recorded
            in the entry as ``"apic_included"`` so restore knows whether
            it may replace the file's cover.

    Returns:
        ``{"path", "size", "mtime", "had_no_header", "apic_included",
        "frames"}``.  ``size``/``mtime`` come from ``os.stat`` at
        snapshot time and are the guard :func:`restore_entry` checks
        before writing anything back.  A file with no ID3 header at all
        (``ID3NoHeaderError``) is not an error: it yields
        ``had_no_header=True`` and ``frames=[]``, which restore turns
        back into "remove the tag entirely".
    """
    path_str = str(path)
    stat = os.stat(path_str)
    try:
        audio = ID3(path_str)
    except ID3NoHeaderError:
        # No tag is a perfectly good "before" state — undoing to it
        # simply means deleting whatever tag was added afterwards.
        return {
            "path": path_str,
            "size": stat.st_size,
            "mtime": int(stat.st_mtime),
            "had_no_header": True,
            "apic_included": bool(include_apic),
            "frames": [],
        }
    return {
        "path": path_str,
        "size": stat.st_size,
        "mtime": int(stat.st_mtime),
        "had_no_header": False,
        "apic_included": bool(include_apic),
        "frames": snapshot_frames(audio, include_apic=include_apic),
    }


def write_undo_file(out_path, entries) -> None:
    """Write *entries* (from :func:`make_entry`) as a gzip JSON undo file.

    The file is ``{"format": "mp3csvtagger-undo", "version": 1,
    "created": <ISO-8601 time>, "files": entries}``.  Gzip is used
    because a snapshot for a large run is still sizeable JSON, and the
    base64 frame data in it compresses well.
    """
    payload = {
        "format": UNDO_FORMAT,
        "version": UNDO_VERSION,
        "created": datetime.now(timezone.utc).isoformat(),
        "files": list(entries),
    }
    out_path_str = str(out_path)
    folder = os.path.dirname(os.path.abspath(out_path_str))
    os.makedirs(folder, exist_ok=True)
    with gzip.open(out_path_str, "wt", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)


def read_undo_file(path) -> dict:
    """Read and validate a gzip JSON undo file written by :func:`write_undo_file`.

    Returns:
        The whole undo-file dict (``format``/``version``/``created``/
        ``files``).

    Raises:
        ValueError: If the file is not an mp3csvtagger undo file (its
            ``"format"`` key is missing or different).
    """
    with gzip.open(str(path), "rt", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict) or payload.get("format") != UNDO_FORMAT:
        raise ValueError(f"{path}: not a {UNDO_FORMAT} undo file")
    return payload


def restore_entry(entry, force: bool = False) -> tuple[str, str]:
    """Restore one file's tags from its undo *entry*.

    Args:
        entry: A dict as produced by :func:`make_entry`.
        force: Restore even if the file's size or mtime no longer match
            the snapshot.  Without this, a changed file is skipped: the
            snapshot belongs to the file as it *was*, and writing old
            frames onto a file something else has since changed could
            tag the wrong audio.

    Returns:
        ``(status, message)`` where status is ``"restored"``,
        ``"skipped"`` (size/mtime guard, and *force* not given), or
        ``"error"`` (for example the file is missing or unreadable).

    Restore semantics: if the snapshot was of a file with no ID3 header,
    the file's tag is removed entirely.  Otherwise every current frame
    is deleted and replaced with the snapshot's frames — except that
    ``PRIV`` frames are always left alone, and ``APIC`` frames are left
    alone too unless the entry's ``apic_included`` is true (in which
    case the snapshot's cover replaces the current one, because the
    current cover is not the snapshotted one).
    """
    path = str(entry["path"])
    try:
        stat = os.stat(path)
    except OSError as exc:
        return "error", f"{path}: cannot stat file: {exc}"

    # Size/mtime guard: see the module docstring.  Cheap, and the only
    # thing standing between a stale snapshot and the wrong file.
    if not force and (stat.st_size != entry["size"] or int(stat.st_mtime) != int(entry["mtime"])):
        return (
            "skipped",
            f"{path}: file changed since snapshot "
            f"(size {stat.st_size} != {entry['size']} or "
            f"mtime {stat.st_mtime} != {entry['mtime']}); "
            "use force to restore anyway",
        )

    try:
        if entry.get("had_no_header"):
            # The "before" state was no tag at all, so undo is deletion.
            _id3_delete(path)
            return "restored", f"{path}: removed ID3 tag (file had no tag before the run)"

        try:
            audio = ID3(path)
        except ID3NoHeaderError:
            # Tag vanished since the snapshot; start from an empty tag
            # and let the snapshot frames fill it.
            audio = ID3()

        apic_included = bool(entry.get("apic_included", False))
        # Delete every current frame the snapshot is allowed to own.
        # Iterate over a copy of the keys: we mutate the tag as we go.
        for key in list(audio.keys()):
            frame = audio[key]
            frame_id = getattr(frame, "FrameID", "")
            if frame_id == "PRIV":
                continue  # private frames are never ours to touch
            if frame_id == "APIC" and not apic_included:
                # The snapshot has no cover (it was excluded to save
                # space), so the live cover must survive the restore.
                continue
            del audio[key]

        for item in entry.get("frames", []):
            frame = pickle.loads(base64.b64decode(item["data"]))
            audio.add(frame)

        audio.save(path)
        return "restored", f"{path}: restored {len(entry.get('frames', []))} frame(s)"
    except Exception as exc:  # one bad file must not abort a whole undo run
        return "error", f"{path}: {exc}"


@dataclass
class UndoResult:
    """Outcome of :func:`undo_run`: counts plus per-file detail."""

    restored: int = 0
    skipped: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    messages: list[str] = field(default_factory=list)


def undo_run(undo_path, force: bool = False, progress=None) -> UndoResult:
    """Apply every entry in the undo file at *undo_path*.

    Args:
        undo_path: Path to a file written by :func:`write_undo_file`.
        force: Passed through to :func:`restore_entry` — restore files
            whose size or mtime have changed since their snapshot.
        progress: Optional ``progress(done, total, path)`` callback,
            called once per file if given.

    Returns:
        An :class:`UndoResult` with the number of files restored, the
        paths skipped by the size/mtime guard, any per-file errors, and
        a human-readable message for every file.  One file failing never
        stops the rest of the run.
    """
    payload = read_undo_file(undo_path)
    entries = payload.get("files", [])
    result = UndoResult()
    for done, entry in enumerate(entries, start=1):
        path = str(entry.get("path", ""))
        if progress is not None:
            progress(done, len(entries), path)
        status, message = restore_entry(entry, force=force)
        result.messages.append(message)
        if status == "restored":
            result.restored += 1
        elif status == "skipped":
            result.skipped.append(path)
        else:  # "error"
            result.errors.append(message)
    return result
