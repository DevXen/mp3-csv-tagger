"""Named column-role presets for CSV entries.

A *preset* is a small, named mapping from CSV column (tag) names to
roles — see :class:`mp3csvtagger.project.Role` (``Match=1``,
``Write=2``, ``Skip=3``).  Applying a preset to a
:class:`mp3csvtagger.project.CsvEntry` sets the role of every column
whose name appears in the preset and leaves all other columns
unchanged, so a common setup (for example "match on the artist,
write the genre") can be reused instead of re-clicking every column.

Presets come in two flavours:

* **Builtins** — shipped with the program, always available, returned
  by :func:`builtin_presets`.
* **User presets** — JSON files in :func:`presets_dir`, written by
  :func:`save_preset` and discovered by :func:`list_presets`.  A user
  preset whose name equals a builtin's name *replaces* that builtin.

On-disk format is a single JSON object, the same shape
:meth:`Preset.to_dict` produces::

    {"name": "My preset", "roles": {"Title": 2, "Genre": 2}}

The presets directory defaults to ``~/.mp3csvtagger/presets`` and
can be overridden with the ``MP3CSVTAGGER_PRESETS_DIR`` environment
variable (used by the tests, and handy for portable installs).
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from .project import CsvEntry, Role

#: Environment variable that overrides the user presets directory.
PRESETS_DIR_ENV_VAR = "MP3CSVTAGGER_PRESETS_DIR"


@dataclass
class Preset:
    """A named set of column roles.

    Attributes:
        name: Human-readable preset name, e.g. ``"Match artist, write genre"``.
        roles: Mapping of CSV column / tag name to role value as an
            ``int`` (see :class:`mp3csvtagger.project.Role`:
            ``Match=1``, ``Write=2``, ``Skip=3``).
    """

    name: str
    roles: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Return a JSON-safe ``dict`` representation of this preset.

        Role values are plain ``int``\\ s, so the result can be passed
        straight to :func:`json.dumps`.
        """
        return {
            "name": self.name,
            "roles": {str(key): int(value) for key, value in self.roles.items()},
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Preset":
        """Build a :class:`Preset` from a ``dict`` such as :meth:`to_dict` output.

        Args:
            data: Mapping with a ``"name"`` key and an optional
                ``"roles"`` mapping of column name to role value.
                Role values are coerced to ``int``.

        Returns:
            The reconstructed preset.
        """
        roles_data = data.get("roles") or {}
        return cls(
            name=str(data["name"]),
            roles={str(key): int(value) for key, value in roles_data.items()},
        )


def presets_dir() -> Path:
    """Return the directory holding user preset JSON files, creating it.

    The directory is ``$MP3CSVTAGGER_PRESETS_DIR`` when that
    environment variable is set and non-empty, otherwise
    ``~/.mp3csvtagger/presets``.  The directory (including parents)
    is created on demand, so callers can always write into the
    returned path.

    Returns:
        The presets directory as a :class:`pathlib.Path`.
    """
    override = os.environ.get(PRESETS_DIR_ENV_VAR)
    if override:
        directory = Path(override).expanduser()
    else:
        directory = Path.home() / ".mp3csvtagger" / "presets"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def builtin_presets() -> list[Preset]:
    """Return the presets shipped with the program.

    A fresh list of fresh :class:`Preset` objects is returned on every
    call, so callers may mutate the result without affecting later
    calls.

    Returns:
        The builtin presets, in display order.
    """
    return [
        Preset(
            name="Match artist, write genre",
            roles={
                "Lead Performer": int(Role.Match),
                "Artist": int(Role.Match),
                "Genre": int(Role.Write),
            },
        ),
        Preset(
            name="Fix titles by filename anchor",
            roles={
                # FileName is an engine pseudo-column, not a real tag;
                # here it is just a column name like any other.
                "FileName": int(Role.Match),
                "Title": int(Role.Write),
            },
        ),
    ]


def _slugify(name: str) -> str:
    """Turn a preset *name* into a safe file-name stem.

    Alphanumerics, ``-`` and ``_`` are kept, spaces become ``-``, and
    every other character is dropped.  Runs of ``-`` are collapsed
    and leading/trailing ``-`` are stripped.

    Args:
        name: The preset name to slugify.

    Returns:
        The slug, or ``"preset"`` if nothing usable remains.
    """
    chars: list[str] = []
    for char in name.strip():
        if char == " ":
            chars.append("-")
        elif char.isalnum() or char in ("-", "_"):
            chars.append(char)
        # Any other character is dropped.
    slug = "".join(chars)
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug.strip("-") or "preset"


def _load_preset_file(path: Path) -> Preset:
    """Load a single preset JSON file from *path*.

    Args:
        path: Path to a JSON file in :meth:`Preset.to_dict` format.

    Returns:
        The preset stored in the file.
    """
    with open(path, encoding="utf-8") as handle:
        return Preset.from_dict(json.load(handle))


def list_presets() -> list[Preset]:
    """List all available presets: builtins plus user presets.

    User presets are read from ``presets_dir()/*.json`` in file-name
    order.  A user preset whose name matches a builtin's name
    replaces that builtin (keeping the builtin's position in the
    list); new user presets are appended after the builtins.
    Unreadable or malformed JSON files are skipped.

    Returns:
        All available presets, builtins first.
    """
    merged: dict[str, Preset] = {}
    order: list[str] = []
    for preset in builtin_presets():
        merged[preset.name] = preset
        order.append(preset.name)
    directory = presets_dir()
    for path in sorted(directory.glob("*.json")):
        try:
            preset = _load_preset_file(path)
        except (OSError, ValueError, KeyError, TypeError):
            continue
        if preset.name not in merged:
            order.append(preset.name)
        merged[preset.name] = preset
    return [merged[name] for name in order]


def save_preset(preset: Preset) -> Path:
    """Save *preset* as a user preset and return the file written.

    The file is ``presets_dir()/<safe name>.json`` where ``<safe
    name>`` is the slugified preset name (see :func:`_slugify`):
    alphanumerics, ``-`` and ``_`` are kept and spaces become ``-``.

    Args:
        preset: The preset to save.

    Returns:
        The :class:`pathlib.Path` of the JSON file that was written.
    """
    directory = presets_dir()
    target = directory / f"{_slugify(preset.name)}.json"
    with open(target, "w", encoding="utf-8") as handle:
        json.dump(preset.to_dict(), handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    return target


def load_preset(name_or_path: str | Path) -> Preset:
    """Load a preset by name or from a JSON file path.

    Resolution order:

    1. If *name_or_path* is an existing file, it is loaded directly.
    2. If ``presets_dir()/<slugified name>.json`` exists, it is loaded.
    3. Otherwise the presets from :func:`list_presets` (user presets
       first in effect, since they replace builtins of the same name)
       are searched by exact name, then case-insensitively.

    Args:
        name_or_path: A preset name, e.g. ``"Match artist, write
            genre"``, or a path to a preset JSON file.

    Returns:
        The requested preset.

    Raises:
        FileNotFoundError: If no file and no preset matches, with a
            message listing the available preset names.
    """
    text = str(name_or_path)
    candidate = Path(name_or_path).expanduser()
    if candidate.is_file():
        return _load_preset_file(candidate)

    # A name saved via save_preset() lives under its slugified name.
    slug_candidate = presets_dir() / f"{_slugify(text)}.json"
    if slug_candidate.is_file():
        return _load_preset_file(slug_candidate)

    available = list_presets()
    for preset in available:
        if preset.name == text:
            return preset
    for preset in available:
        if preset.name.lower() == text.lower():
            return preset

    names = ", ".join(repr(preset.name) for preset in available) or "(none)"
    raise FileNotFoundError(
        f"Preset not found: {text!r}. No file exists at {str(candidate)!r} "
        f"and no builtin or user preset has that name. "
        f"Available presets: {names}."
    )


def apply_preset(entry: CsvEntry, preset: Preset) -> int:
    """Apply *preset*'s roles to the columns of a CSV *entry*.

    For each tag on *entry* whose name is in ``preset.roles``, the
    tag's role is set to the preset's value.  Columns that are not
    named in the preset are left unchanged, and preset entries that
    name columns the entry does not have are ignored.

    Args:
        entry: The CSV entry to update in place.
        preset: The preset whose roles should be applied.

    Returns:
        How many columns (tags) were set.
    """
    count = 0
    for tag in entry.tags:
        if tag.name in preset.roles:
            tag.role = int(preset.roles[tag.name])
            count += 1
    return count
