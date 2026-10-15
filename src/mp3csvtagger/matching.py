"""Value normalisation for *Match* columns.

A CSV row belongs to an MP3 file when the file's current tag value
compares equal to the CSV value after:

* lower-casing both sides, and
* deleting every character in :data:`string.punctuation`.

So ``"Rage Against the Machine"``, ``"rage against the machine"`` and
``"Rage Against The Machine!"`` all match each other, but extra words do not.
Surrounding whitespace is trimmed as well.

Crucially, normalisation is applied **once per value** and cached. See
:mod:`mp3csvtagger.preview` for the hash index built on top of it — that
combination is what makes matching fast even on large libraries.
"""

from __future__ import annotations

import string
from functools import lru_cache

# Translation table that deletes all ASCII punctuation.
_PUNCTUATION = str.maketrans("", "", string.punctuation)


@lru_cache(maxsize=65536)
def normalize(value: str | None) -> str:
    """Return the comparison form of *value* (``""`` for ``None``)."""
    if not value:
        return ""
    return value.strip().lower().translate(_PUNCTUATION).strip()
