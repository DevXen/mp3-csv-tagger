# MP3 CSV Tagger

**Bulk-edit MP3 ID3 tags from CSV files.** Point it at a folder of MP3s and
one or more spreadsheets: rows are matched to files by the tag values you
choose, and the values you choose get written — with a full preview first,
and a change log afterwards so you can always see (or undo) what happened.

This is a fast, open-source rewrite of a 2019 program that had become
painfully slow. Same workflow, same CSV format, same rules — a new engine.
On a test library of 600 MP3s matched against a 600-row CSV, a full
scan + preview takes **about a second**. The story of the original, what
was recovered from it, and why it crawled is in
[docs/ORIGINAL_PROGRAM.md](docs/ORIGINAL_PROGRAM.md); the recovered 2019
sources are preserved in [original-recovered/](original-recovered/).

## How it works

1. **Files** — add MP3 files or whole folders.
2. **CSV files** — add one or more CSVs. Each *column* gets a role:
   * **Match** — a row applies only to files whose current value for this
     column equals the row's value (case and punctuation are ignored, so
     `dont stop` matches `Don't Stop!`).
   * **Write** — the row's value replaces the file's value for this column.
   * **Skip** — the column is ignored (default for new columns).
3. **Preview** — see every file that matches and exactly what would change,
   before anything is written. If several rows offer different values for
   the same tag, the last CSV layer wins and you can pick another value.
4. **Apply** — writes the tags and saves a change log CSV
   (`mp3tag_YYYYMMDD_HHMMSS.log.csv`) recording old → new for every tag.

CSVs are **layers**: they run in order, and a later CSV can Match on a
value an earlier CSV writes. That is how the included example fixes
genres in one pass and then rates everything that just got that genre in
the next.

Column headings can be ID3 frame ids (`TIT2`), friendly names (`Title`,
`Lead Performer`, `Artist`, …) or your own field names — an unknown heading
becomes a custom `TXXX` tag named after the heading. Friendly names are
editable in the Setup tab. Full detail: [docs/CSV_FORMAT.md](docs/CSV_FORMAT.md).

## Install & run

Requires Python 3.10+ and [mutagen](https://mutagen.readthedocs.io/)
(the only dependency; the GUI is Python's built-in Tkinter).

```bash
pip install mp3csvtagger        # or, from a clone:  pip install .
mp3csvtagger                    # opens the desktop app
```

Prefer no window? Everything is scriptable:

```bash
# One-shot dry run (add --apply to write)
mp3csvtagger run --folder ~/Music --csv tags.csv \
  --csv-roles "Lead Performer=Match,Genre=Write,Rating=Write"

# …or with a saved project (the same file the GUI opens)
mp3csvtagger new project.mp3p.json
mp3csvtagger add-files project.mp3p.json --folder ~/Music
mp3csvtagger add-csv project.mp3p.json tags.csv \
  --roles "Lead Performer=Match,Genre=Write,Rating=Write"
mp3csvtagger preview project.mp3p.json --out preview.csv
mp3csvtagger apply project.mp3p.json
```

Try it in two minutes with the sample library:

```bash
python examples/make_sample_mp3s.py     # builds examples/library/
# then follow examples/README.md
```

## Building a standalone program (no Python needed to run it)

* **Windows `.exe`** — `build_windows.bat` (PyInstaller, 64-bit). See
  [docs/BUILDING.md](docs/BUILDING.md). This replaces the old "extract a
  zip of DLLs and hope" distribution: one folder, one exe, modern Python.
* **Linux/macOS** — `pip install .` plus the same PyInstaller spec if you
  want a single-file build.
* **Android** — scoped in [docs/ANDROID.md](docs/ANDROID.md): the engine is
  small and portable, but Android needs a native tag library, so the app is
  a planned companion rather than a repackage of this code.

## Why the rewrite is faster

* The original compared every CSV row against every file and re-normalised
  every value on every comparison. This one builds a **hash index** on the
  normalised Match values: each value is processed once, and a row finds
  its files with one lookup.
* The original stored its preview in SQLite with a **commit per tag**.
  This one computes the preview in memory.
* Scanning reads files in **parallel**; applying opens and saves each
  changed file **once**.
* Files with no ID3 header no longer crash the run; they simply start
  empty.

## Documentation

* [User guide](docs/USER_GUIDE.md) — the full workflow, tab by tab
* [CSV format](docs/CSV_FORMAT.md) — headings, roles, matching rules, layers
* [Building](docs/BUILDING.md) — Windows exe, development setup
* [Android plan](docs/ANDROID.md)
* [The original program](docs/ORIGINAL_PROGRAM.md) — recovery & post-mortem

## License

MIT. Free for everyone, forever — see [LICENSE](LICENSE).
