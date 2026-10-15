"""A project: the MP3 paths, the CSV layers and the settings for a run.

The original stored projects as a SQLite database copied to a temp file
(``.mp3p``), and its preview lived in the same database — with a commit after
almost every single tag. That design is the main reason it was slow.

This rewrite keeps a project as plain data classes and saves it as readable
JSON (``.mp3p.json``). A preview is computed in memory in milliseconds and is
never stored in the project at all.

CSV entries are *layers*: they apply in list order, so when two included
CSVs write the same tag on the same file, the later CSV's value is the one
selected by default (the earlier value stays available as an alternative the
user can pick, just like the original's "multiple values" dialog).
"""

from __future__ import annotations

import enum
import json
import os
from dataclasses import dataclass, field

from .csvfiles import CsvFile
from .tags import DEFAULT_ALTERNATIVE_NAMES


class Role(enum.IntEnum):
    """What a CSV column does. Values match the original program's."""

    Match = 1  # row applies only to files whose current value equals the CSV value
    Write = 2  # the CSV value replaces the file's value
    Skip = 3   # column is ignored (the original's default for new columns)


@dataclass
class CsvTag:
    """One CSV column: its heading and its role."""

    name: str
    role: int = int(Role.Skip)

    def to_dict(self) -> dict:
        return {"name": self.name, "role": int(self.role)}

    @classmethod
    def from_dict(cls, data: dict) -> "CsvTag":
        return cls(name=data["name"], role=int(data.get("role", Role.Skip)))


@dataclass
class CsvEntry:
    """One CSV file in the layer stack."""

    path: str
    included: bool = True
    tags: list[CsvTag] = field(default_factory=list)

    @property
    def filename(self) -> str:
        return os.path.basename(self.path)

    def refresh_tags(self) -> None:
        """Re-read the file's headings, keeping roles for columns that remain.

        New columns start as :attr:`Role.Skip`, exactly like the original.
        """
        headings = CsvFile(self.path).headings()
        old_roles = {tag.name: tag.role for tag in self.tags}
        self.tags = [
            CsvTag(name=heading, role=old_roles.get(heading, int(Role.Skip)))
            for heading in headings
        ]

    def columns(self, role: Role) -> list[tuple[int, CsvTag]]:
        """``(zero-based column index, tag)`` pairs for one role, in order."""
        return [
            (index, tag)
            for index, tag in enumerate(self.tags)
            if int(tag.role) == int(role)
        ]

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "included": self.included,
            "tags": [tag.to_dict() for tag in self.tags],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "CsvEntry":
        return cls(
            path=data["path"],
            included=bool(data.get("included", True)),
            tags=[CsvTag.from_dict(tag) for tag in data.get("tags", [])],
        )


@dataclass
class Project:
    """Everything needed to build a preview and apply it."""

    mp3_paths: list[str] = field(default_factory=list)
    csv_entries: list[CsvEntry] = field(default_factory=list)
    #: Frame id -> friendly name, editable in Setup.
    alternative_names: dict[str, str] = field(
        default_factory=lambda: dict(DEFAULT_ALTERNATIVE_NAMES)
    )
    #: Folder where Apply writes its ``mp3tag_YYYYMMDD_HHMMSS.log.csv`` change log.
    apply_log_folder: str = field(
        default_factory=lambda: os.path.join(os.path.expanduser("~"), "mp3tagging")
    )

    # -- MP3 paths ---------------------------------------------------------
    def add_mp3_path(self, path: str) -> None:
        path = path.replace("/", os.sep)
        if path not in self.mp3_paths:
            self.mp3_paths.append(path)

    def remove_mp3_path(self, path: str) -> None:
        if path in self.mp3_paths:
            self.mp3_paths.remove(path)

    # -- CSV entries -------------------------------------------------------
    def add_csv_file(self, path: str) -> CsvEntry:
        path = path.replace("/", os.sep)
        if any(entry.path == path for entry in self.csv_entries):
            raise ValueError(f"Another CSV entry for the same path already exists: {path}")
        entry = CsvEntry(path=path)
        entry.refresh_tags()  # raises CsvError if unreadable
        self.csv_entries.append(entry)
        return entry

    def move_csv_entry(self, entry: CsvEntry, direction: int) -> None:
        """Move an entry up (``-1``) or down (``+1``) in the layer order."""
        index = self.csv_entries.index(entry)
        target = index + direction
        if 0 <= target < len(self.csv_entries):
            self.csv_entries[index], self.csv_entries[target] = (
                self.csv_entries[target],
                self.csv_entries[index],
            )

    # -- Persistence -------------------------------------------------------
    def to_dict(self) -> dict:
        return {
            "format": "mp3csvtagger-project",
            "version": 1,
            "mp3_paths": list(self.mp3_paths),
            "csv_entries": [entry.to_dict() for entry in self.csv_entries],
            "alternative_names": dict(self.alternative_names),
            "apply_log_folder": self.apply_log_folder,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Project":
        project = cls(
            mp3_paths=list(data.get("mp3_paths", [])),
            alternative_names=dict(
                data.get("alternative_names") or DEFAULT_ALTERNATIVE_NAMES
            ),
            apply_log_folder=data.get("apply_log_folder")
            or os.path.join(os.path.expanduser("~"), "mp3tagging"),
        )
        project.csv_entries = [
            CsvEntry.from_dict(entry) for entry in data.get("csv_entries", [])
        ]
        return project

    def save(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(self.to_dict(), handle, indent=2, ensure_ascii=False)

    @classmethod
    def load(cls, path: str) -> "Project":
        with open(path, encoding="utf-8") as handle:
            return cls.from_dict(json.load(handle))
