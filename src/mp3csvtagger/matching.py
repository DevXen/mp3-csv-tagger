"""Value normalisation for *Match* columns.

The original program decided that a CSV row belongs to an MP3 file by
comparing the file's current tag value against the CSV value after:

* lower-casing both sides, and
* deleting every character in :data:`string.punctuation`.

So ``"Rage Against the Machine"``, ``"rage against the machine"`` and
``"Rage Against The Machine!"`` all match each other, but extra words do not.

This module keeps exactly that rule (plus trimming surrounding whitespace,
which the original got away with only because its test CSVs were tidy) and,
crucially, it is applied **once per value**. The original re-ran it inside a
triple-nested loop for every (row, file, tag) combination — one of the big
reasons it crawled. See :mod:`mp3csvtagger.preview` for the hash index that
replaces that loop.
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
