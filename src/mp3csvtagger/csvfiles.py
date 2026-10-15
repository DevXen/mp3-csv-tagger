"""Reading the CSV files that drive a tagging run.

CSV format (same as the original program expected):

* UTF-8, comma-separated, first row is the header.
* Each header is a tag name — a frame id (``TIT2``), a friendly name
  (``Title``, ``Lead Performer``) or a custom field name (stored as ``TXXX``).
* Each following row is one candidate set of values. Rows are *not* tied to
  files by filename: a row is applied to every MP3 whose **Match** columns
  equal the row's values. See ``docs/CSV_FORMAT.md``.
"""

from __future__ import annotations

import csv
import os


class CsvError(RuntimeError):
    """Raised when a CSV file cannot be read."""


class CsvFile:
    """A CSV file on disk: its headings plus a streaming row iterator."""

    CHAR_ENCODING = "utf-8-sig"  # utf-8, but tolerates Excel's BOM

    def __init__(self, path: str):
        self.path = path

    @property
    def filename(self) -> str:
        return os.path.basename(self.path)

    def headings(self) -> list[str]:
        """Return the header row (column tag names, in order)."""
        try:
            with open(self.path, newline="", encoding=self.CHAR_ENCODING) as handle:
                reader = csv.reader(handle)
                for row in reader:
                    return [heading.strip() for heading in row]
        except OSError as exc:
            raise CsvError(f"Unable to read CSV file: {self.path} ({exc})") from exc
        return []

    def rows(self):
        """Yield ``(row_index, values)`` — row_index is 1-based, data rows only."""
        try:
            handle = open(self.path, newline="", encoding=self.CHAR_ENCODING)
        except OSError as exc:
            raise CsvError(f"Unable to read CSV file: {self.path} ({exc})") from exc
        with handle:
            reader = csv.reader(handle)
            headings = next(reader, None)
            if not headings:
                return
            width = len(headings)
            for index, row in enumerate(reader, start=1):
                if not row or all(cell == "" for cell in row):
                    continue  # skip blank lines, like the original did
                # Pad/truncate ragged rows instead of crashing (original died).
                values = (row + [""] * width)[:width]
                yield index, values


def write_csv(path: str, header: list[str], rows) -> None:
    """Write *rows* to *path* as a CSV with *header* (used for change logs)."""
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, delimiter=",", quotechar='"', quoting=csv.QUOTE_MINIMAL)
        writer.writerow(header)
        writer.writerows(rows)
