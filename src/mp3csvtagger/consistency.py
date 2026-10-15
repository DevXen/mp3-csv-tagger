"""Tags-vs-path consistency: do the tags agree with the file layout?

Many libraries encode the same facts twice — once in folder and file
names (``Artist/Album/01 - Title.mp3``) and once in the tags inside the
files. When the two disagree, one of them is wrong, and a tagging run
built on the wrong one makes the mess permanent. This module compares
the two, read-only:

* :func:`check_consistency` captures values from each file's path with
  a filename pattern (see :mod:`mp3csvtagger.filename_tags`) and
  compares each captured value against the value actually stored in
  the file's tags, using the same loose comparison as matching
  (case and punctuation do not count as disagreements).
* :func:`render_consistency_text` and :func:`render_consistency_csv`
  format the findings.

Read-only is structural here, not just a promise: this module imports
only from the value-*reading* parts of the project (filename capture,
normalisation, scanning and frame resolution). It has no access to
anything that can write a tag, so a consistency report can never
change a file — it can only point at the disagreements and let the
user decide which side is right.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field

from .filename_tags import capture_for_file
from .matching import normalize
from .mp3files import Mp3File
from .tags import frame_for_tag_name


@dataclass
class ConsistencyMismatch:
    """One tag whose path-captured value disagrees with its stored value.

    ``path_value`` is the value the file's path/name claims the tag
    holds; ``tag_value`` is the value actually stored in the file
    (which may be empty — an empty tag under a path that names a value
    is a disagreement, not a pass).
    """

    path: str
    tag: str
    path_value: str
    tag_value: str


@dataclass
class ConsistencyResult:
    """The outcome of a consistency check over a set of files."""

    mismatches: list[ConsistencyMismatch] = field(default_factory=list)
    #: How many files' paths matched the pattern and were compared.
    checked: int = 0
    #: Paths whose name/path did NOT match the pattern (not compared).
    unmatched: list[str] = field(default_factory=list)
    #: Total files examined (checked + unmatched).
    files_checked: int = 0


def check_consistency(
    files: list[Mp3File],
    pattern: str,
    *,
    root: str | None = None,
    use_path: bool = True,
    alternative_names: dict[str, str] | None = None,
) -> ConsistencyResult:
    """Compare each file's tags against the values its path captures.

    *pattern* is a filename pattern as in
    :mod:`mp3csvtagger.filename_tags`; with *use_path* (the default)
    it is matched against the file's path relative to *root*, so
    folder names can be captured too, and with ``use_path=False``
    against the file name alone.

    For every captured tag, the captured value and the stored value
    (read via :meth:`Mp3File.value_for`, honouring
    *alternative_names*) are compared after
    :func:`~mp3csvtagger.matching.normalize`. A tag is skipped only
    when *both* sides normalise to empty; any other disagreement —
    including a stored value that is empty while the path names one —
    is recorded as a mismatch, in file order, then pattern order.

    Files whose path does not match the pattern are not compared at
    all; they are listed in the result's ``unmatched``.
    """
    result = ConsistencyResult(files_checked=len(files))
    for mp3 in files:
        captured = capture_for_file(pattern, mp3.path, root=root, use_path=use_path)
        if captured is None:
            result.unmatched.append(mp3.path)
            continue
        result.checked += 1
        for tag_name, path_value in captured.items():
            frame = frame_for_tag_name(tag_name, alternative_names)
            tag_value = mp3.value_for(tag_name, frame)
            if not normalize(path_value) and not normalize(tag_value):
                continue  # both sides effectively empty: nothing to compare
            if normalize(path_value) == normalize(tag_value):
                continue
            result.mismatches.append(
                ConsistencyMismatch(
                    path=mp3.path,
                    tag=tag_name,
                    path_value=path_value,
                    tag_value=tag_value,
                )
            )
    return result


def render_consistency_text(result: ConsistencyResult, pattern: str) -> str:
    """Render a consistency result as plain text for console or file.

    States the pattern used, the coverage (files examined, files whose
    paths matched, files whose paths did not), and then every mismatch
    with both values shown — the path's claim and the tag's reality —
    followed by the unmatched files, so a report always accounts for
    every file that was examined.
    """
    lines: list[str] = [
        "Tags vs path consistency",
        "========================",
        "",
        f"Pattern: {pattern}",
        f"Files examined: {result.files_checked}",
        f"Files checked: {result.checked}",
        f"Files not matching the pattern: {len(result.unmatched)}",
        "",
        f"Mismatches: {len(result.mismatches)}",
    ]
    if not result.mismatches:
        lines.append("  (none)")
    for mismatch in result.mismatches:
        lines.append(f"  {mismatch.path}")
        lines.append(
            f'    {mismatch.tag}: from path "{mismatch.path_value}" '
            f'vs in tags "{mismatch.tag_value}"'
        )
    lines.append("")
    lines.append("Not matching the pattern:")
    if not result.unmatched:
        lines.append("  (none)")
    for path in result.unmatched:
        lines.append(f"  {path}")
    return "\n".join(lines) + "\n"


def render_consistency_csv(result: ConsistencyResult) -> str:
    """Render the mismatches as CSV text: Path,Tag,From Path,In Tags.

    One row per mismatch, so the findings can be filtered and sorted
    in a spreadsheet. Files that matched cleanly and files that did
    not match the pattern produce no rows — the CSV is a work list of
    disagreements only.
    """
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(["Path", "Tag", "From Path", "In Tags"])
    for mismatch in result.mismatches:
        writer.writerow(
            [mismatch.path, mismatch.tag, mismatch.path_value, mismatch.tag_value]
        )
    return buffer.getvalue()
