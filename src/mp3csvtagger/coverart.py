"""Cover art (``APIC``) helpers.

Cover art is not a text tag: an MP3 carries it as an ``APIC`` frame holding
raw image bytes, a MIME type and a picture type.  This module keeps the
small pieces of that handling in one place:

* which image files are supported and what MIME type they map to,
* resolving a cover-art value from a CSV (a path, possibly relative to the
  CSV file) to a real file on disk,
* building the ``APIC`` frame to store in an MP3, and
* how a cover-art value is shown in a preview.

By convention a blank cover-art value means "remove the existing cover
art"; see :func:`cover_display`.
"""

from __future__ import annotations

import os

from mutagen.id3 import APIC

#: Friendly tag name used for cover art in CSV columns / the UI.
COVER_TAG_NAME = "Cover Art"

#: Supported image file extensions (lower-case, with dot) -> MIME type.
IMAGE_MIMES = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png"}

__all__ = [
    "COVER_TAG_NAME",
    "IMAGE_MIMES",
    "mime_for_image",
    "resolve_image_path",
    "make_cover_frame",
    "cover_display",
]


def mime_for_image(path) -> str:
    """Return the MIME type for the image file at *path*.

    The type is decided purely from the file extension (case-insensitive):
    ``.jpg`` / ``.jpeg`` -> ``image/jpeg`` and ``.png`` -> ``image/png``.

    Args:
        path: Path (or path-like / string) of the image file.

    Returns:
        The MIME type string, e.g. ``"image/png"``.

    Raises:
        ValueError: If the extension is not supported.  The message lists
            the supported types.
    """
    extension = os.path.splitext(str(path))[1].lower()
    mime = IMAGE_MIMES.get(extension)
    if mime is None:
        supported = ", ".join(sorted(IMAGE_MIMES))
        raise ValueError(
            f"Unsupported cover image type {extension or '(no extension)'!r} "
            f"for {path!r}: supported types are {supported} "
            f"({', '.join(sorted(set(IMAGE_MIMES.values())))})"
        )
    return mime


def resolve_image_path(value, csv_dir=None) -> str:
    """Resolve a cover-art *value* to an absolute path of an existing file.

    Absolute values are used as-is.  Relative values are resolved against
    *csv_dir* (typically the folder containing the CSV the value came from)
    or, when *csv_dir* is not given, against the current working directory.

    Args:
        value: The image path as written in the CSV / project.
        csv_dir: Optional base directory for relative values.

    Returns:
        The absolute (normalised) path of the image file.

    Raises:
        FileNotFoundError: If the resolved path does not name a file.
    """
    text = str(value).strip()
    if os.path.isabs(text):
        candidate = text
    else:
        base = str(csv_dir) if csv_dir else os.getcwd()
        candidate = os.path.join(base, text)
    absolute = os.path.abspath(candidate)
    if not os.path.isfile(absolute):
        raise FileNotFoundError(f"Cover image not found: {absolute}")
    return absolute


def make_cover_frame(image_path):
    """Build a front-cover ``APIC`` frame from the image at *image_path*.

    The frame uses UTF-8 text encoding (``encoding=3``), the MIME type
    implied by the file extension (see :func:`mime_for_image`), picture
    type 3 (front cover), an empty description, and the file's raw bytes
    as its data.

    Args:
        image_path: Path of a supported image file (``.jpg`` / ``.jpeg`` /
            ``.png``).

    Returns:
        A :class:`mutagen.id3.APIC` frame ready to add to an ID3 tag.

    Raises:
        ValueError: If the image type is not supported.
        FileNotFoundError: If *image_path* does not exist (from opening it).
    """
    mime = mime_for_image(image_path)
    with open(image_path, "rb") as handle:
        data = handle.read()
    return APIC(encoding=3, mime=mime, type=3, desc="", data=data)


def cover_display(value) -> str:
    """Return the short preview display string for a cover-art *value*.

    A blank / whitespace-only (or ``None``) value means the cover art is
    to be removed, shown as ``"[remove cover art]"``.  Any other value is
    the path of a cover image and is shown as
    ``"[cover image: <basename>]"`` — the full path would swamp a preview
    table, and the bytes themselves obviously cannot be shown as text.

    Args:
        value: The cover-art value from a CSV cell (a path, or blank).

    Returns:
        The display string described above.
    """
    if value is None or not str(value).strip():
        return "[remove cover art]"
    basename = os.path.basename(str(value).strip())
    return f"[cover image: {basename}]"
