"""Read-only analysis of a scanned library: duplicates and variants.

Tagging a library is much easier once its existing problems are visible.
This module answers two questions about a list of scanned
:class:`~mp3csvtagger.mp3files.Mp3File` objects — without changing
anything:

* :func:`duplicate_groups` — which files appear to be the *same track*
  (same title and same lead performer, compared after
  :func:`~mp3csvtagger.matching.normalize`, so case and punctuation
  differences do not hide a duplicate)?
* :func:`variant_groups` — for one tag, which *values* are really the
  same value spelled more than one way (``"Beatles"`` / ``"beatles"``
  / ``"BEATLES!"``)? Those are the values a cleanup pass would want to
  unify — this module only reports them; renaming values is a decision
  for the user, never something a report does on its own.

:func:`render_text_report` formats both answers as a plain-text report
suitable for the console or a file, and :func:`render_csv_report`
formats the same findings as CSV rows (one row per affected file) for
spreadsheet use.
"""

from __future__ import annotations

import csv
import io

from .matching import normalize
from .mp3files import Mp3File
from .tags import frame_for_tag_name

#: Friendly name / frame used for the two values that identify a track.
_TITLE_NAME, _TITLE_FRAME = "Title", "TIT2"
_ARTIST_NAME, _ARTIST_FRAME = "Lead Performer", "TPE1"


def duplicate_groups(files: list[Mp3File]) -> list[dict]:
    """Group files that look like duplicate copies of the same track.

    Two files are duplicates when their Title (``TIT2``) and Lead
    Performer (``TPE1``) values are equal after
    :func:`~mp3csvtagger.matching.normalize` — values are looked up via
    :meth:`Mp3File.value_for`, so tags stored under either the friendly
    name or the frame id are found. Files missing either value are
    skipped: with no title or no artist there is not enough evidence to
    call anything a duplicate.

    Returns a list of ``{"title": ..., "artist": ..., "paths": [...]}``
    dicts — title and artist are the as-stored (un-normalised) spellings
    from the first file in the group, and ``paths`` are in scan order.
    Only groups of more than one file are returned, sorted by
    (normalised) artist, then title.
    """
    groups: dict[tuple[str, str], dict] = {}
    for mp3 in files:
        title = mp3.value_for(_TITLE_NAME, _TITLE_FRAME)
        artist = mp3.value_for(_ARTIST_NAME, _ARTIST_FRAME)
        key = (normalize(title), normalize(artist))
        if not key[0] or not key[1]:
            continue
        group = groups.get(key)
        if group is None:
            group = {"title": title, "artist": artist, "paths": []}
            groups[key] = group
        group["paths"].append(mp3.path)

    duplicates = [group for group in groups.values() if len(group["paths"]) > 1]
    duplicates.sort(key=lambda g: (normalize(g["artist"]), normalize(g["title"])))
    return duplicates


def variant_groups(
    files: list[Mp3File],
    tag_name: str,
    alternative_names: dict[str, str] | None = None,
) -> list[dict]:
    """Find values of *tag_name* that are spelled more than one way.

    Files are grouped by the normalised form of their value for
    *tag_name* (resolved to a frame with
    :func:`~mp3csvtagger.tags.frame_for_tag_name`, honouring
    *alternative_names* when given, and read via
    :meth:`Mp3File.value_for`). A group is reported only when that one
    normalised value occurs with more than one distinct actual spelling
    — e.g. ``"Beatles"``, ``"beatles"`` and ``"BEATLES!"`` all normalise
    to ``"beatles"`` but are three spellings. Empty values are skipped.
    Note that normalisation only folds case and punctuation (see
    :mod:`mp3csvtagger.matching`): ``"The Beatles"`` normalises to
    ``"the beatles"``, a *different* value from ``"beatles"``.

    Returns a list of ``{"tag": tag_name, "normalized": ...,
    "spellings": {spelling: [paths]}}`` dicts, sorted by the normalised
    value. Spellings are the values as stored (stripped of surrounding
    whitespace), and each spelling's paths are in scan order.
    """
    frame = frame_for_tag_name(tag_name, alternative_names)
    by_normalized: dict[str, dict[str, list[str]]] = {}
    for mp3 in files:
        value = mp3.value_for(tag_name, frame).strip()
        if not value:
            continue
        normalized = normalize(value)
        if not normalized:
            continue
        spellings = by_normalized.setdefault(normalized, {})
        spellings.setdefault(value, []).append(mp3.path)

    return [
        {"tag": tag_name, "normalized": normalized, "spellings": spellings}
        for normalized, spellings in sorted(by_normalized.items())
        if len(spellings) > 1
    ]


def _flatten_variant_groups(variant_groups_list) -> list[dict]:
    """Accept variant groups as one flat list or as a list of lists.

    Callers naturally hold either the result of a single
    :func:`variant_groups` call (a flat list of group dicts) or the
    results of several calls, one per tag (a list of such lists). Both
    shapes render the same way.
    """
    flattened: list[dict] = []
    for item in variant_groups_list or []:
        if isinstance(item, dict):
            flattened.append(item)
        else:
            flattened.extend(item)
    return flattened


def render_text_report(duplicates, variant_groups_list) -> str:
    """Render duplicates and spelling variants as a plain-text report.

    *duplicates* is a list as returned by :func:`duplicate_groups`;
    *variant_groups_list* is a list as returned by
    :func:`variant_groups`, or a list of such lists (one per tag
    checked). The report has a section per kind of finding, each headed
    with its counts, and lists every affected path indented under the
    value it belongs to. Empty sections say ``(none)`` rather than
    disappearing, so a clean library still produces a complete report.
    """
    duplicates = list(duplicates or [])
    variants = _flatten_variant_groups(variant_groups_list)

    lines: list[str] = ["Library report", "==============", ""]

    duplicate_files = sum(len(group["paths"]) for group in duplicates)
    lines.append(
        f"Duplicates: {len(duplicates)} group(s), {duplicate_files} file(s)"
    )
    if not duplicates:
        lines.append("  (none)")
    for group in duplicates:
        lines.append(
            f'  "{group["title"]}" by {group["artist"]} '
            f'({len(group["paths"])} file(s))'
        )
        for path in group["paths"]:
            lines.append(f"    {path}")
    lines.append("")

    variant_spellings = sum(len(group["spellings"]) for group in variants)
    lines.append(
        f"Spelling variants: {len(variants)} group(s), "
        f"{variant_spellings} spelling(s)"
    )
    if not variants:
        lines.append("  (none)")
    for group in variants:
        lines.append(
            f'  {group["tag"]}: "{group["normalized"]}" '
            f'({len(group["spellings"])} spelling(s))'
        )
        for spelling, paths in group["spellings"].items():
            lines.append(f'    "{spelling}" ({len(paths)} file(s))')
            for path in paths:
                lines.append(f"      {path}")

    return "\n".join(lines) + "\n"


#: Column order for :func:`render_csv_report`. One row per affected
#: file keeps the CSV flat enough to filter/sort in a spreadsheet,
#: which is the point of exporting findings out of the text report.
CSV_REPORT_COLUMNS = (
    "Kind", "Tag", "Title", "Artist", "Normalized", "Spelling", "File",
)


def render_csv_report(duplicates, variant_groups_list) -> str:
    """Render duplicates and spelling variants as CSV text.

    Same inputs as :func:`render_text_report`. Columns are
    :data:`CSV_REPORT_COLUMNS`: duplicate rows carry the group's
    Title/Artist and leave the variant columns blank; variant rows
    carry the Tag, the normalised value, and the spelling as stored in
    that file. There is one row per affected file, so a duplicate
    group of three files produces three rows.
    """
    duplicates = list(duplicates or [])
    variants = _flatten_variant_groups(variant_groups_list)

    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(CSV_REPORT_COLUMNS)
    for group in duplicates:
        for path in group["paths"]:
            writer.writerow(
                ["duplicate", "", group["title"], group["artist"], "", "", path]
            )
    for group in variants:
        for spelling, paths in group["spellings"].items():
            for path in paths:
                writer.writerow(
                    ["variant", group["tag"], "", "", group["normalized"],
                     spelling, path]
                )
    return buffer.getvalue()
