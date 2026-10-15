"""Building the preview: which files match which CSV rows, and what changes.

Matching is the heart of the program, so it is built to avoid the two
classic traps: comparing every CSV row against every file (an
O(rows × files × tags) scan), and persisting intermediate results.
The algorithm here instead:

1. scans each MP3 **once** (in parallel, see :mod:`.mp3files`),
2. for each CSV layer, builds a **hash index** from the normalised Match
   values of the files to the files themselves — each value is normalised
   exactly once — so a CSV row finds its files with one dict lookup,
3. keeps the whole preview in memory as plain dataclasses. No database.

Layering is preserved: after a CSV layer runs, its selected writes become the
files' *effective* values, so a later CSV can Match on a value an earlier
CSV is going to write.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import mp3files as mp3mod
from .csvfiles import CsvFile
from .library_export import PSEUDO_COLUMNS, pseudo_value
from .matching import normalize
from .project import Project, Role
from .tags import frame_for_tag_name

#: Display value used as a cover-art cell's "old value" when a file
#: already has embedded art. The image bytes are never loaded for a
#: preview; presence is all a change decision needs.
COVER_PRESENT = "[cover image]"

#: Source name recorded on a candidate the user typed into the preview
#: by hand (an inline manual edit). It shows up wherever a candidate's
#: source is displayed — including the change log's Source column — so
#: a hand-typed value is always distinguishable from a CSV value.
MANUAL_SOURCE = "manual edit"

#: Layer number for manual edits. Real CSV layers are numbered by their
#: position in the project and virtual layers start at 1000 (see
#: :func:`add_value_layer`), so a layer of a million sorts a manual edit
#: after every value any layer could produce: the value the user typed
#: most recently is the one that wins.
MANUAL_LAYER = 1_000_000


def pseudo_column_name(tag_name: str) -> str | None:
    """Canonical pseudo-column name for *tag_name*, or ``None``.

    Pseudo-columns (``FileName``, ``FilePath``, ``Folder``) describe where
    a file lives instead of a tag inside it. They can be matched but
    never written — file names and paths are a *source* of values in
    this program, never a target.
    """
    for pseudo in PSEUDO_COLUMNS:
        if tag_name.strip().lower() == pseudo.lower():
            return pseudo
    return None


def old_value_for(mp3_file: mp3mod.Mp3File, tag_name: str, frame: str) -> str:
    """The display/ comparison "old value" of one tag on one file."""
    if frame == "APIC":
        return COVER_PRESENT if mp3_file.has_cover else ""
    return mp3_file.value_for(tag_name, frame)


@dataclass
class Candidate:
    """One value a CSV row wants to write, and where it came from."""

    value: str
    csv_name: str
    csv_row_index: int
    layer: int  # position of the CSV entry in the project (0-based)
    #: Full path of the source CSV ("" for virtual layers); cover-art
    #: values are image paths resolved relative to this file's folder.
    csv_path: str = ""
    #: True only for a value the user typed into the preview by hand
    #: (see :meth:`Cell.set_manual_edit`). Manual candidates are kept
    #: distinct from layered candidates so they can be replaced or
    #: cleared without disturbing the values the layers produced.
    manual: bool = False


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
        """The selected candidate's value (the old value if none)."""
        if not self.candidates:
            return self.old_value
        return self.candidates[self.selected].value

    @property
    def changed(self) -> bool:
        """True when the selected value differs from the file's current one."""
        return bool(self.candidates) and self.value != self.old_value

    @property
    def has_multiple(self) -> bool:
        """True when the cell holds more than one candidate value."""
        return len(self.candidates) > 1

    def add_candidate(self, candidate: Candidate) -> None:
        """Add a candidate; identical values are merged, newest is selected."""
        for index, existing in enumerate(self.candidates):
            if existing.value == candidate.value:
                self.selected = index
                return
        self.candidates.append(candidate)
        self.selected = len(self.candidates) - 1

    @property
    def manual_candidate(self) -> Candidate | None:
        """The manual-edit candidate on this cell, or ``None``.

        At most one manual candidate ever exists per cell —
        :meth:`set_manual_edit` replaces it rather than stacking edits.
        """
        for candidate in self.candidates:
            if candidate.manual:
                return candidate
        return None

    def set_manual_edit(self, value: str) -> None:
        """Record a value the user typed into this cell by hand.

        Any previous manual candidate is dropped, the new value is
        appended as a manual candidate (source :data:`MANUAL_SOURCE`,
        layer :data:`MANUAL_LAYER`) and selected. Because a manual edit
        is an ordinary selected candidate from this point on, Apply,
        the change log and snapshot undo all handle it with no special
        cases — the log simply records its source as "manual edit".
        """
        self.candidates = [c for c in self.candidates if not c.manual]
        self.candidates.append(
            Candidate(
                value=value,
                csv_name=MANUAL_SOURCE,
                csv_row_index=-1,
                layer=MANUAL_LAYER,
                manual=True,
            )
        )
        self.selected = len(self.candidates) - 1

    def clear_manual_edit(self) -> None:
        """Remove the manual edit, re-selecting the last remaining value.

        The candidates the layers produced are still on the cell, so
        clearing an edit falls back to the newest of them (the same
        value that would have been selected had the edit never
        happened). A no-op when the cell has no manual candidate.
        """
        if self.manual_candidate is None:
            return
        self.candidates = [c for c in self.candidates if not c.manual]
        self.selected = len(self.candidates) - 1 if self.candidates else 0


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
        """How many of this row's cells would change the file."""
        return sum(1 for cell in self.cells.values() if cell.changed)


@dataclass
class Preview:
    """The result of building a preview: matched rows + scan metadata."""
    rows: list[PreviewRow] = field(default_factory=list)
    #: Write-column tag names, in the order the CSVs first use them.
    write_tags: list[str] = field(default_factory=list)
    files_scanned: int = 0
    scan_errors: list[str] = field(default_factory=list)
    #: Counter for virtual layers (filename captures, lookups, …) so their
    #: candidates sort after every real CSV layer.
    virtual_layer_count: int = 0

    @property
    def files_matched(self) -> int:
        """Number of files that matched at least one row."""
        return len(self.rows)

    @property
    def total_changes(self) -> int:
        """Total number of changed cells across all rows."""
        return sum(row.change_count for row in self.rows)

    def row_for_path(self, path: str) -> PreviewRow | None:
        """The preview row for *path*, or None."""
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
        # Pseudo-columns are computed from the file's location and never
        # change during a run, so they win over the tag dictionaries.
        """A tag's current effective value on a file (pseudo-columns win)."""
        pseudo = pseudo_column_name(tag_name)
        if pseudo is not None:
            return pseudo_value(by_path[path], pseudo)
        if frame == "APIC":
            return COVER_PRESENT if by_path[path].has_cover else ""
        tags = effective[path]
        if tag_name in tags:
            return tags[tag_name]
        return tags.get(frame, "")

    for layer, entry in enumerate(project.csv_entries):
        if not entry.included:
            continue
        match_cols = entry.columns(Role.Match)
        write_cols = entry.columns(Role.Write)
        # Writing to a pseudo-column would mean renaming/moving files,
        # which this program never does — reject it loudly, not silently.
        for _i, tag in write_cols:
            if pseudo_column_name(tag.name) is not None:
                raise ValueError(
                    f"Column {tag.name!r} in {entry.filename} is a file "
                    "location, not a tag: it can be used to Match, but "
                    "never to Write."
                )
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
                            old_value=old_value_for(by_path[path], tag.name, frame),
                        )
                        row.cells[tag.name] = cell
                    cell.add_candidate(
                        Candidate(
                            value=values[i],
                            csv_name=entry.filename,
                            csv_row_index=row_index,
                            layer=layer,
                            csv_path=entry.path,
                        )
                    )
        # This layer's selected writes become effective for the next layer.
        for row in preview.rows:
            for tag_name, cell in row.cells.items():
                if any(candidate.layer == layer for candidate in cell.candidates):
                    effective[row.path][tag_name] = cell.value
                    effective[row.path][cell.frame] = cell.value

    return preview


def empty_preview(files: list[mp3mod.Mp3File]) -> Preview:
    """A preview over already-scanned *files* with no layers applied yet.

    Virtual-layer flows (filename captures, lookups, report fixes) start
    here and then add their values with :func:`add_value_layer`, so they
    end up in exactly the same preview/apply path as CSV changes.
    """
    return Preview(
        files_scanned=len(files),
        scan_errors=[f"{f.path}: {f.error}" for f in files if f.error],
    )


def add_value_layer(
    preview: Preview,
    files: list[mp3mod.Mp3File],
    values_by_path: dict[str, dict[str, str]],
    source_name: str,
    alternative_names: dict[str, str] | None = None,
) -> int:
    """Add one virtual layer of write values to *preview*; return cell count.

    ``values_by_path`` maps a file path to ``{tag name: value}``. Each
    value becomes a candidate (source *source_name*, row 0) on that
    file's cell for the tag, creating rows and cells as needed — the
    same structures a CSV layer produces, so preview display, value
    choosing and Apply all work unchanged.
    """
    by_path = {f.path: f for f in files}
    rows_by_path = {row.path: row for row in preview.rows}
    layer = 1000 + preview.virtual_layer_count
    preview.virtual_layer_count += 1
    added = 0
    for path, values in values_by_path.items():
        mp3_file = by_path.get(path)
        if mp3_file is None:
            continue
        row = rows_by_path.get(path)
        if row is None:
            row = PreviewRow(path=path, filename=mp3_file.filename)
            rows_by_path[path] = row
            preview.rows.append(row)
        for tag_name, value in values.items():
            frame = frame_for_tag_name(tag_name, alternative_names)
            cell = row.cells.get(tag_name)
            if cell is None:
                cell = Cell(
                    tag_name=tag_name,
                    frame=frame,
                    old_value=old_value_for(mp3_file, tag_name, frame),
                )
                row.cells[tag_name] = cell
            if tag_name not in preview.write_tags:
                preview.write_tags.append(tag_name)
            cell.add_candidate(
                Candidate(
                    value=value,
                    csv_name=source_name,
                    csv_row_index=0,
                    layer=layer,
                )
            )
            added += 1
    return added
