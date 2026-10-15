# MP3 CSV Tagger

**Bulk-edit MP3 ID3 tags from CSV files.** Point it at a folder of MP3s and
one or more spreadsheets: rows are matched to files by the tag values you
choose, and the values you choose get written — with a full preview first,
a change log afterwards, and a tag-snapshot undo if you change your mind.
On a test library of 600 MP3s matched against a 600-row CSV, a full
scan + preview takes **about a second**.

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
4. **Apply** — writes the tags, saves a change log CSV
   (`mp3tag_YYYYMMDD_HHMMSS.log.csv`) recording old → new for every tag,
   plus an undo snapshot of the tags it replaced (audio is never copied).

CSVs are **layers**: they run in order, and a later CSV can Match on a
value an earlier CSV writes. That is how the included example fixes
genres in one pass and then rates everything that just got that genre in
the next. You only ever *need* one CSV — layering is there when your
data comes from more than one place.

Column headings can be ID3 frame ids (`TIT2`), friendly names (`Title`,
`Lead Performer`, `Artist`, …), your own field names — an unknown heading
becomes a custom `TXXX` tag named after the heading — the pseudo-columns
`FileName`, `FilePath` and `Folder` (match on where a file lives), or
`Cover Art` (embed or remove cover images). Friendly names are editable
in the Setup tab. Full detail: [docs/CSV_FORMAT.md](docs/CSV_FORMAT.md).

## More than CSVs

* **Tags from filenames** — your file names and folder layout already
  follow a pattern (`Artist/Album/01 - Title.mp3`); capture tag values
  from them with a pattern like `{Lead Performer} - {Title}`. File names
  are a *source* of tag values — the program never renames files.
* **Export library → CSV** — dump every file's tags to a spreadsheet,
  fix them there, feed the sheet back as a Write layer. Exports can
  also **append**: build one library CSV up folder by folder, with
  re-scanned files updating their rows in place.
* **Library report** — find duplicate tracks and inconsistent spellings
  (`Beatles` vs `beatles` vs `BEATLES`) and unify them with an explicit pick.
* **Role presets** — save a column-role setup once, reuse it on every
  new CSV; two presets ship built in.
* **Cover art & lyrics** — embed front-cover images from a CSV column,
  remove them with a blank cell; lyrics are an ordinary text column.
* **MusicBrainz fill (opt-in)** — for files whose Title and Artist are
  present, look up missing Album / Year / Genre / Recording Date and
  preview the results like any other change. Nothing is fetched unless
  you ask, and nothing is written without the preview.
* **Undo** — every Apply saves a compact snapshot of the *tags* it
  replaced (never copies of the audio). `mp3csvtagger undo <run>.undo`
  or the Apply tab's "Undo a run…" restores them, skipping any file
  that changed since the run.

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
mp3csvtagger undo  ~/mp3tagging/mp3tag_20261015_103708.undo
mp3csvtagger export --folder ~/Music --out library.csv
```

Try it in two minutes with the sample library:

```bash
python examples/make_sample_mp3s.py     # builds examples/library/
# then follow examples/README.md
```

## Building a standalone program (no Python needed to run it)

* **Windows `.exe`** — `build_windows.bat` (PyInstaller, 64-bit). See
  [docs/BUILDING.md](docs/BUILDING.md): one folder, one exe, modern Python.
* **Linux/macOS** — `pip install .` plus the same PyInstaller spec if you
  want a single-file build.
* **Android** — a native Kotlin companion app lives in
  [android/](android/) and shares the CSV format, roles and rules;
  see [docs/ANDROID.md](docs/ANDROID.md).

## Why it is fast

* Matching builds a **hash index** on the normalised Match values: each
  value is processed once, and a row finds its files with one lookup —
  no rows × files × tags scan.
* The preview is computed **in memory** as plain data — no database
  round-trips per tag.
* Scanning reads files in **parallel**; applying opens and saves each
  changed file **once**.
* Undo snapshots store only the replaced tags, so even a 10,000-file
  run leaves a small undo file, not a copy of your library.
* Files with no ID3 header are handled, not fatal: they simply start
  empty.

## Documentation

* [Help](docs/HELP.md) — the full in-app help text, topic by topic
* [User guide](docs/USER_GUIDE.md) — the workflow, tab by tab
* [CSV format](docs/CSV_FORMAT.md) — headings, roles, matching rules, layers
* [Building](docs/BUILDING.md) — Windows exe, development setup
* [Android](docs/ANDROID.md) — the companion app

## License

MIT. Free for everyone, forever — see [LICENSE](LICENSE).
