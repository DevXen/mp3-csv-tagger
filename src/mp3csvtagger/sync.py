"""Two-library tag sync: copy tags from one library onto its twin.

The situation this is built for: the same library exists in two places
(a main copy and a backup / laptop / re-rip copy) and the *tags* of one
copy have been fixed up while the other copy's have not. Sync pairs the
two copies up file by file and copies the source copy's tag values onto
the target copy — through an ordinary preview, so the user sees every
proposed change, can pick candidates, and gets the usual change log
and snapshot undo when they apply it.

Pairing is by *relative path*: ``Music/Artist/Album/01 Song.mp3`` in
the source library pairs with the same relative path in the target
library, compared case-insensitively with ``"/"`` separators, so a
library moved between a case-sensitive and a case-insensitive
filesystem still pairs up. Files that do not pair by path are reported
as unpaired and are **never** touched by a sync preview; a second pass
(:func:`pair_leftovers_by_fingerprint`) can pair some of those
leftovers by audio fingerprint instead — see :mod:`.fingerprints`.

Nothing in this module writes to any MP3. Building a preview is all it
does; writing stays with :mod:`.apply`, exactly like a CSV run.
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, field

from mutagen.id3 import ID3

from . import mp3files as mp3mod
from .preview import COVER_PRESENT, Preview, add_value_layer, empty_preview
from .tags import frame_for_tag_name

#: Source name recorded on every candidate a sync preview produces, so
#: the preview, the change log and the undo flow can all tell these
#: values apart from CSV values.
SYNC_SOURCE_NAME = "tag sync"

#: Tag name used for cover art in sync differences and previews. Cover
#: art is an ``APIC`` frame, not a text tag; see :mod:`.coverart`.
COVER_TAG_NAME = "Cover Art"


@dataclass
class SyncPair:
    """One source file and the target file it is the twin of."""

    #: The pairing key: the files' shared relative path (see
    #: :func:`relative_key`), or the source file's base name for pairs
    #: made by fingerprint, where no shared relative path exists.
    rel_key: str
    source_path: str
    target_path: str


@dataclass
class SyncPlan:
    """How two libraries pair up: the pairs plus both leftover lists."""

    pairs: list[SyncPair] = field(default_factory=list)
    #: Source paths with no target partner. Never touched by a sync.
    unpaired_source: list[str] = field(default_factory=list)
    #: Target paths with no source partner. Never touched by a sync.
    unpaired_target: list[str] = field(default_factory=list)


def relative_key(root: str, path: str) -> str:
    """The pairing key for *path* under library root *root*.

    The path relative to *root*, with ``"/"`` separators and
    casefolded, so ``Artist/Album/Song.mp3`` and
    ``artist/album/song.mp3`` — the same file on filesystems that
    differ only in case handling — produce the same key.
    """
    relative = os.path.relpath(path, root)
    return relative.replace(os.sep, "/").casefold()


def pair_libraries(
    source_root,
    target_root,
    *,
    source_files=None,
    target_files=None,
) -> SyncPlan:
    """Pair two libraries by relative path and return the plan.

    *source_files* / *target_files* are pre-scanned
    :class:`~mp3csvtagger.mp3files.Mp3File` lists; when either is not
    given, that library's root is scanned now. Pairs follow the source
    files' order; each target file pairs at most once.
    """
    if source_files is None:
        source_files = mp3mod.scan([str(source_root)])
    if target_files is None:
        target_files = mp3mod.scan([str(target_root)])

    targets_by_key: dict[str, str] = {}
    for target in target_files:
        # First target wins on a key collision: two target files whose
        # relative paths differ only in case cannot both be the twin.
        targets_by_key.setdefault(relative_key(str(target_root), target.path), target.path)

    plan = SyncPlan()
    paired_targets: set[str] = set()
    for source in source_files:
        key = relative_key(str(source_root), source.path)
        target_path = targets_by_key.get(key)
        if target_path is None or target_path in paired_targets:
            plan.unpaired_source.append(source.path)
            continue
        paired_targets.add(target_path)
        plan.pairs.append(
            SyncPair(rel_key=key, source_path=source.path, target_path=target_path)
        )
    plan.unpaired_target = [
        target.path for target in target_files if target.path not in paired_targets
    ]
    return plan


def pair_leftovers_by_fingerprint(plan, fingerprints, durations) -> SyncPlan:
    """Pair a plan's leftovers that are the same recording; new plan.

    A leftover source file pairs with a leftover target file when both
    have a fingerprint, the fingerprint *strings* are equal, and their
    durations differ by at most 2.0 seconds (the duration check guards
    against the rare fingerprint collision between different edits of
    a song). Durations come from the *durations* mapping when it has
    the path, falling back to the fingerprint's own duration. Each file
    pairs at most once, and the original *plan* is not modified.
    """
    fingerprints = fingerprints or {}
    durations = durations or {}

    def duration_of(path: str) -> float | None:
        if path in durations:
            return float(durations[path])
        fingerprint = fingerprints.get(path)
        return float(fingerprint.duration) if fingerprint is not None else None

    result = SyncPlan(
        pairs=list(plan.pairs),
        unpaired_source=[],
        unpaired_target=list(plan.unpaired_target),
    )
    for source_path in plan.unpaired_source:
        source_fp = fingerprints.get(source_path)
        if source_fp is None:
            result.unpaired_source.append(source_path)
            continue
        source_duration = duration_of(source_path)
        match_index = None
        for index, target_path in enumerate(result.unpaired_target):
            target_fp = fingerprints.get(target_path)
            if target_fp is None or target_fp.fingerprint != source_fp.fingerprint:
                continue
            target_duration = duration_of(target_path)
            if (
                source_duration is not None
                and target_duration is not None
                and abs(source_duration - target_duration) > 2.0
            ):
                continue
            match_index = index
            break
        if match_index is None:
            result.unpaired_source.append(source_path)
            continue
        target_path = result.unpaired_target.pop(match_index)
        result.pairs.append(
            SyncPair(
                # No shared relative path exists for a fingerprint pair;
                # the source base name is the most useful key to show.
                rel_key=os.path.basename(source_path).casefold(),
                source_path=source_path,
                target_path=target_path,
            )
        )
    return result


def _cover_bytes(path: str) -> bytes | None:
    """The first ``APIC`` image's bytes in the file at *path*, or None.

    A scan records only *whether* a file has a cover (see
    :class:`~mp3csvtagger.mp3files.Mp3File`), because image bytes are
    large. Sync is the one flow that must compare and copy them, so it
    reads them here, on demand, for paired files only.
    """
    try:
        audio = ID3(path)
    except Exception:
        return None
    if audio is None:
        return None
    for frame in audio.getall("APIC"):
        data = getattr(frame, "data", None)
        if data:
            return bytes(data)
    return None


def _cover_mime(path: str) -> str:
    """The MIME type of the first ``APIC`` image in *path* ("" if none)."""
    try:
        audio = ID3(path)
    except Exception:
        return ""
    if audio is None:
        return ""
    for frame in audio.getall("APIC"):
        return str(getattr(frame, "mime", "") or "")
    return ""


def _extract_cover(source_path: str, cover_dir: str) -> str | None:
    """Write the source file's cover image into *cover_dir*; return its path.

    The file is named ``sync-cover-<sha1[:12]>.<ext>`` after the image
    bytes themselves, so the same cover shared by an album extracts
    once and re-running a sync reuses the same file. The extension
    follows the image's MIME type (``.png`` for PNG, ``.jpg``
    otherwise), because apply decides how to embed an image from its
    extension — see :mod:`.coverart`. Returns ``None`` when the source
    file has no cover bytes to extract.
    """
    data = _cover_bytes(source_path)
    if not data:
        return None
    extension = ".png" if "png" in _cover_mime(source_path).lower() else ".jpg"
    digest = hashlib.sha1(data).hexdigest()[:12]
    os.makedirs(cover_dir, exist_ok=True)
    image_path = os.path.abspath(
        os.path.join(cover_dir, f"sync-cover-{digest}{extension}")
    )
    if not os.path.exists(image_path):
        with open(image_path, "wb") as handle:
            handle.write(data)
    return image_path


def default_sync_tags(plan, source_files) -> list[str]:
    """The default tag set for a sync: every text tag on paired sources.

    The union of the tag names found on the plan's paired source files,
    in first-seen order. Callers render these as checkboxes and pass
    the checked subset to :func:`tag_differences` /
    :func:`build_sync_preview`. Cover art is not a text tag and is
    handled by the separate ``include_cover`` flag, so it never appears
    here; nothing else is excluded.
    """
    by_path = {f.path: f for f in source_files}
    tags: list[str] = []
    for pair in plan.pairs:
        source = by_path.get(pair.source_path)
        if source is None:
            continue
        for tag_name in source.tags:
            if tag_name and tag_name not in tags:
                tags.append(tag_name)
    return tags


def tag_differences(
    plan,
    source_files,
    target_files,
    tags,
    *,
    include_cover,
    alternative_names=None,
) -> list[dict]:
    """List where paired files' tags differ (for display / dry runs).

    Returns one ``{"target_path", "source_path", "tag", "source_value",
    "target_value"}`` dict per (pair, tag) whose source value is
    non-empty and differs from the target's — exactly the values
    :func:`build_sync_preview` would copy. With *include_cover*, a pair
    whose cover images differ (and whose source has one) also produces
    a row with tag ``"Cover Art"`` and the display value
    ``"[cover image]"``. Unpaired files never appear.
    """
    sources = {f.path: f for f in source_files}
    targets = {f.path: f for f in target_files}
    differences: list[dict] = []
    for pair in plan.pairs:
        source = sources.get(pair.source_path)
        target = targets.get(pair.target_path)
        if source is None or target is None:
            continue
        for tag_name in tags or []:
            frame = frame_for_tag_name(tag_name, alternative_names)
            source_value = source.value_for(tag_name, frame)
            target_value = target.value_for(tag_name, frame)
            if source_value and source_value != target_value:
                differences.append(
                    {
                        "target_path": pair.target_path,
                        "source_path": pair.source_path,
                        "tag": tag_name,
                        "source_value": source_value,
                        "target_value": target_value,
                    }
                )
        if include_cover:
            source_cover = _cover_bytes(pair.source_path)
            if source_cover and source_cover != _cover_bytes(pair.target_path):
                differences.append(
                    {
                        "target_path": pair.target_path,
                        "source_path": pair.source_path,
                        "tag": COVER_TAG_NAME,
                        "source_value": COVER_PRESENT,
                        "target_value": COVER_PRESENT if target.has_cover else "",
                    }
                )
    return differences


def build_sync_preview(
    plan,
    source_files,
    target_files,
    tags,
    *,
    include_cover,
    cover_dir,
    alternative_names=None,
) -> Preview:
    """Build the preview that copies the chosen tags source -> target.

    The preview covers the *target* files (they are the ones that would
    be written) and carries one virtual layer named ``"tag sync"``. A
    tag is copied only when the source value is non-empty and differs
    from the target value — copying an identical or empty value would
    either be noise or would *erase* a target value the source never
    had, and sync must never do either.

    Cover art: with *include_cover*, when the source file's cover bytes
    differ from the target's, the source image is extracted into
    *cover_dir* (see :func:`_extract_cover`) and the cell's value is
    that image's absolute path under the tag name ``"Cover Art"`` —
    apply resolves an absolute image path as-is and, because an APIC
    cell changed, snapshots the target's old cover for undo.

    Unpaired files never appear in the preview.
    """
    preview = empty_preview(target_files)
    sources = {f.path: f for f in source_files}
    targets = {f.path: f for f in target_files}

    values_by_path: dict[str, dict[str, str]] = {}
    for pair in plan.pairs:
        source = sources.get(pair.source_path)
        target = targets.get(pair.target_path)
        if source is None or target is None:
            continue
        values: dict[str, str] = {}
        for tag_name in tags or []:
            frame = frame_for_tag_name(tag_name, alternative_names)
            source_value = source.value_for(tag_name, frame)
            target_value = target.value_for(tag_name, frame)
            if source_value and source_value != target_value:
                values[tag_name] = source_value
        if include_cover:
            source_cover = _cover_bytes(pair.source_path)
            if source_cover and source_cover != _cover_bytes(pair.target_path):
                image_path = _extract_cover(pair.source_path, str(cover_dir))
                if image_path is not None:
                    values[COVER_TAG_NAME] = image_path
        if values:
            values_by_path[pair.target_path] = values

    if values_by_path:
        add_value_layer(
            preview,
            target_files,
            values_by_path,
            source_name=SYNC_SOURCE_NAME,
            alternative_names=alternative_names,
        )
    return preview
