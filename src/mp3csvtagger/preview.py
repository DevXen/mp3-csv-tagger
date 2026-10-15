"""Building the preview: which files match which CSV rows, and what changes.

This is where the original program spent almost all of its time, and how it
did it explains the "runs very slow" complaint:

* for **every CSV row** it looped over **every MP3 file** and **every tag**,
  re-normalising the same values (lower-case + strip punctuation) on every
  single comparison — an O(rows × files × tags) scan with the expensive part
  in the innermost loop;
* every intermediate result was written to SQLite with a ``commit()`` per tag.

The algorithm here instead:

1. scans each MP3 **once** (in parallel, see :mod:`.mp3files`),
2. for each CSV layer, builds a **hash index** from the normalised Match
   values of the files to the files themselves — each value is normalised
   exactly once — so a CSV row finds its files with one dict lookup,
3. keeps the whole preview in memory as plain dataclasses. No database.

Layering is preserved: after a CSV layer runs, its selected writes become the
files' *effective* values, so a later CSV can Match on a value an earlier
CSV is going to write — the original tracked that too
(``write_value_tracking``), it just did it the slow way.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import mp3files as mp3mod
from .csvfiles import CsvFile
from .matching import normalize
from .project import Project, Role
from .tags import frame_for_tag_name


@dataclass
class Candidate:
    """One value a CSV row wants to write, and where it came from."""

    value: str
    csv_name: str
    csv_row_index: int
    layer: int  # position of the CSV entry in the project (0-based)


@dataclass
class Cell:
    """All candidate values for one (file, tag), with one selected."""

    tag_name: str
    frame: str
    old_value: str  # value currently stored in the file on disk
    candidates: list[Candidate] = field(default_factory=list)
    selected: int = 0  # index into candidates; the last layer wins by default

    @property
    def value(self) -> str:
        if not self.candidates:
            return self.old_value
        return self.candidates[self.selected].value

    @property
    def changed(self) -> bool:
        return bool(self.candidates) and self.value != self.old_value

    @property
    def has_multiple(self) -> bool:
        return len(self.candidates) > 1

    def add_candidate(self, candidate: Candidate) -> None:
        """Add a candidate; identical values are merged, newest is selected."""
        for index, existing in enumerate(self.candidates):
            if existing.value == candidate.value:
                self.selected = index
                return
        self.candidates.append(candidate)
        self.selected = len(self.candidates) - 1


@dataclass
class PreviewRow:
    """One matched MP3 file and everything the run would write to it."""

    path: str
    filename: str
    #: Match column tag name -> the file's value that matched (for display).
    matches: dict[str, str] = field(default_factory=dict)
    cells: dict[str, Cell] = field(default_factory=dict)  # tag name -> cell

    @property
    def change_count(self) -> int:
        return sum(1 for cell in self.cells.values() if cell.changed)


@dataclass
class Preview:
    rows: list[PreviewRow] = field(default_factory=list)
    #: Write-column tag names, in the order the CSVs first use them.
    write_tags: list[str] = field(default_factory=list)
    files_scanned: int = 0
    scan_errors: list[str] = field(default_factory=list)

    @property
    def files_matched(self) -> int:
        return len(self.rows)

    @property
    def total_changes(self) -> int:
        return sum(row.change_count for row in self.rows)

    def row_for_path(self, path: str) -> PreviewRow | None:
        for row in self.rows:
            if row.path == path:
                return row
        return None


def build_preview(
    project: Project,
    files: list[mp3mod.Mp3File] | None = None,
    *,
    progress=None,
) -> Preview:
    """Compute the full preview for *project*.

    Pass pre-scanned *files* to reuse a scan (the GUI does this); otherwise
    the project's MP3 paths are scanned now.
    """
    if files is None:
        files = mp3mod.scan(project.mp3_paths, progress=progress)

    preview = Preview(
        files_scanned=len(files),
        scan_errors=[f"{f.path}: {f.error}" for f in files if f.error],
    )
    rows_by_path: dict[str, PreviewRow] = {}
    # Effective values per file: starts as the on-disk tags, updated after
    # each layer with that layer's selected writes (see module docstring).
    effective: dict[str, dict[str, str]] = {
        f.path: dict(f.tags) for f in files
    }
    by_path = {f.path: f for f in files}

    def effective_value(path: str, tag_name: str, frame: str) -> str:
        tags = effective[path]
        if tag_name in tags:
            return tags[tag_name]
        return tags.get(frame, "")

    for layer, entry in enumerate(project.csv_entries):
        if not entry.included:
            continue
        match_cols = entry.columns(Role.Match)
        write_cols = entry.columns(Role.Write)
        if not write_cols:
            continue
        for _index, tag in write_cols:
            if tag.name not in preview.write_tags:
                preview.write_tags.append(tag.name)

        # --- Hash index: normalised match key -> files -------------------
        if match_cols:
            index: dict[tuple[str, ...], list[str]] = {}
            for f in files:
                key = tuple(
                    normalize(
                        effective_value(
                            f.path,
                            tag.name,
                            frame_for_tag_name(tag.name, project.alternative_names),
                        )
                    )
                    for _i, tag in match_cols
                )
                index.setdefault(key, []).append(f.path)
        else:
            index = None  # no Match columns: every row applies to every file

        csv_file = CsvFile(entry.path)
        for row_index, values in csv_file.rows():
            if index is None:
                target_paths = [f.path for f in files]
            else:
                key = tuple(normalize(values[i]) for i, _tag in match_cols)
                target_paths = index.get(key, [])
            for path in target_paths:
                row = rows_by_path.get(path)
                if row is None:
                    row = PreviewRow(
                        path=path, filename=by_path[path].filename
                    )
                    rows_by_path[path] = row
                    preview.rows.append(row)
                for i, tag in match_cols:
                    row.matches[tag.name] = effective_value(
                        path,
                        tag.name,
                        frame_for_tag_name(tag.name, project.alternative_names),
                    )
                for i, tag in write_cols:
                    frame = frame_for_tag_name(tag.name, project.alternative_names)
                    cell = row.cells.get(tag.name)
                    if cell is None:
                        cell = Cell(
                            tag_name=tag.name,
                            frame=frame,
                            old_value=by_path[path].value_for(tag.name, frame),
                        )
                        row.cells[tag.name] = cell
                    cell.add_candidate(
                        Candidate(
                            value=values[i],
                            csv_name=entry.filename,
                            csv_row_index=row_index,
                            layer=layer,
                        )
                    )
        # This layer's selected writes become effective for the next layer.
        for row in preview.rows:
            for tag_name, cell in row.cells.items():
                if any(candidate.layer == layer for candidate in cell.candidates):
                    effective[row.path][tag_name] = cell.value
                    effective[row.path][cell.frame] = cell.value

    return preview
