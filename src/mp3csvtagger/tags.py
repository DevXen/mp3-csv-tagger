"""ID3 frame bookkeeping: names, friendly aliases and frame creation.

Terminology used across the whole project (same as the original program):

* **Tag name** — what a CSV column heading says, e.g. ``TIT2``, ``Title`` or
  ``My Custom Field``.
* **Frame** — the actual ID3 frame that gets stored in the MP3, e.g. ``TIT2``.
* **Alternative / friendly name** — a human name for a frame, e.g. the frame
  ``TPE1`` is shown as "Lead Performer".

Resolution rules for a CSV heading (first hit wins):

1. The heading *is* a known ID3 frame id (``TIT2``) → that frame.
2. The heading matches a friendly name, case-insensitively (``title``,
   ``Lead Performer``, ``Artist``) → the mapped frame. The map is editable per
   project (Setup tab / ``alternative_names`` in the project file); the
   original shipped with only four entries (TPE1/TPE2/TPE3/TPUB), this rewrite
   seeds the common ones below and still lets you override or remove any.
3. Anything else → a custom ``TXXX`` frame whose description is the heading,
   exactly like the original (its log is full of ``Custom Tag = TXXX``).
"""

from __future__ import annotations

from mutagen import id3

#: Frames that carry no editable text for our purposes. The original skipped
#: ``PRIV`` and ``APIC`` (embedded pictures / private data) when reading.
IGNORED_FRAMES = {"PRIV", "APIC"}

#: Friendly name -> frame id. Keys are stored in the project file in the
#: original's orientation (frame -> friendly name); see
#: :func:`frame_for_tag_name`.
DEFAULT_ALTERNATIVE_NAMES: dict[str, str] = {
    # frame: friendly name   (the original's four are marked *)
    "TPE1": "Lead Performer",   # *
    "TPE2": "Band",             # *
    "TPE3": "Conductor",        # *
    "TPUB": "Publisher",        # *
    "TIT2": "Title",
    "TALB": "Album",
    "TCON": "Genre",
    "TYER": "Year",
    "TDRC": "Recording Date",
    "TRCK": "Track Number",
    "TPOS": "Disc Number",
    "TCOM": "Composer",
    "TPE4": "Remixer",
    "TIT1": "Grouping",
    "TIT3": "Subtitle",
    "TBPM": "BPM",
    "TKEY": "Key",
    "TLAN": "Language",
    "TCOP": "Copyright",
    "TENC": "Encoded By",
    "TEXT": "Lyricist",
    "COMM": "Comment",
    "USLT": "Lyrics",
}

#: Extra friendly aliases that all point at the same frame. These are accepted
#: when *reading* a heading but are not the name shown back to the user.
_EXTRA_ALIASES: dict[str, str] = {
    "artist": "TPE1",
    "performer": "TPE1",
    "album artist": "TPE2",
    "date": "TDRC",
    "track": "TRCK",
    "disc": "TPOS",
}


def frame_for_tag_name(
    tag_name: str, alternative_names: dict[str, str] | None = None
) -> str:
    """Resolve a CSV heading / tag name to an ID3 frame id (or ``TXXX``)."""
    name = (tag_name or "").strip()
    if not name:
        return "TXXX"
    # 1. A real frame id, e.g. "TIT2" (case-insensitive) or "TXXX:Something".
    upper = name.upper()
    if upper.startswith("TXXX:"):
        return "TXXX"
    if hasattr(id3, upper) and len(upper) == 4:
        return upper
    # 2. Friendly names: project map first, then the extra aliases.
    names = alternative_names if alternative_names is not None else DEFAULT_ALTERNATIVE_NAMES
    for frame, friendly in names.items():
        if friendly.lower() == name.lower():
            return frame.upper()
    if name.lower() in _EXTRA_ALIASES:
        return _EXTRA_ALIASES[name.lower()]
    # 3. Unknown heading -> custom text frame, like the original.
    return "TXXX"


def is_known_frame(tag_name: str, alternative_names: dict[str, str] | None = None) -> bool:
    """True when *tag_name* resolves to a standard frame rather than TXXX."""
    return frame_for_tag_name(tag_name, alternative_names) != "TXXX"


def frame_text(tag: object) -> str:
    """Return the text of a mutagen frame as one string (``""`` if none).

    The original concatenated a frame's text list with no separator; we keep
    that so values compare the same way they did before.
    """
    text = getattr(tag, "text", None)
    if text is None:
        return ""
    if isinstance(text, list):
        return "".join(str(part) for part in text)
    return str(text)


def tag_name_and_value(tag: object) -> tuple[str, str] | None:
    """Map a mutagen frame to ``(tag_name, value)``, or ``None`` to skip it.

    For ``TXXX`` frames the tag name is the frame's description, which is how
    custom CSV columns find their existing values again on the next run.
    """
    frame_id = getattr(tag, "FrameID", "")
    if frame_id in IGNORED_FRAMES:
        return None
    if frame_id == "TXXX":
        return (str(getattr(tag, "desc", "") or ""), frame_text(tag))
    return (frame_id, frame_text(tag))


def create_frame(frame_id: str, tag_name: str, value: str):
    """Build a new mutagen frame holding *value*.

    Mirrors the original ``create_tag``: use the frame class's ``text``
    attribute when it has one, fall back to ``data`` / ``url``, and give
    ``TXXX`` frames the original tag name as their description.
    """
    frame_class = getattr(id3, frame_id, None) or id3.TXXX
    frame = frame_class()
    if isinstance(frame, id3.TXXX):
        frame.desc = tag_name
    if getattr(frame, "text", None) is not None or hasattr(frame_class, "text"):
        frame.text = [value]
        return frame
    if hasattr(frame, "data"):
        frame.data = value.encode("utf-8", errors="replace")
        return frame
    if hasattr(frame, "url"):
        frame.url = value
        return frame
    raise RuntimeError(
        f"Cannot find an appropriate attribute for value (tried text, data, "
        f"url) in tag class: {frame_class!r}"
    )
