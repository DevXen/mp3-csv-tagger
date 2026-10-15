# Changelog

## 1.5.0 — 2026-10-15

Desktop 1.4.0 + Android app 1.2.0. Everything below works through
the same preview → apply → change log → tag-snapshot undo path as
CSV changes, on both platforms unless noted.

* **Edit values in the preview** — double-click a preview cell
  (Android: tap it) and type the correction. A manual edit outranks
  every CSV candidate, is marked "✎ manual edit", and can be
  reverted to the candidate value. The change log gains a trailing
  **Source** column on both platforms — the CSV file name, or the
  feature that produced the value ("manual edit", "tag sync", …).
* **Two-library tag sync** — pair files by relative path
  (case/separator-insensitive), choose which tags to copy plus an
  optional cover-art copy, and get a normal preview of the target
  library. A tag copies only when the source value is non-empty and
  differs; unpaired files are listed and never touched. Desktop:
  "Sync tags…" dialog + `sync-tags` CLI. Android: "Sync tags from
  another folder…".
* **Fingerprint matching (desktop)** — with the external `fpcalc`
  (Chromaprint) tool detected on PATH, sync can also pair leftover
  files by identical fingerprint + duration, and the library report
  gains a "Same recordings" section — groups sharing a fingerprint
  with differing tags, with a unify-from-one-file action through
  the preview. Fingerprints are cached by path/size/mtime.
  **AcoustID** lookup is opt-in with your own free API key (Setup),
  rate-limited, fills only empty Title/Lead Performer/Album/Year,
  as a preview. No key = no network. See ROADMAP for why Android
  does not fingerprint.
* **Tags-vs-path consistency report** — read-only on both
  platforms: apply a `{Tag}` filename/path pattern to every file
  and list where the stored tags disagree with the path-implied
  values. The report module has no write path at all; the CLI is
  `report --pattern`, the GUIs have a "Consistency check…" dialog.
* **Album-grouped preview + completeness** — the preview can group
  rows by album (desktop toggle, Android checkbox), and a
  completeness report counts per album how many tracks have Title,
  Lead Performer, Album, Year, Genre, Track Number and Cover Art,
  with a library-wide summary (`report --completeness` on the CLI;
  Android's library report also covers duplicates and spelling
  variants now).
* **Saved jobs** — a named bundle of folders, CSV layers + roles
  and filename-pattern layers, saved once and rerun in one step
  (desktop Files tab or `jobs` / `job-save` / `job-run`; Android
  "Save current job…" / "Jobs…", plus launcher dynamic shortcuts
  that open a job straight into its preview).
* **Small things** — desktop drag & drop of files/folders/CSVs
  onto the Files tab when the optional `tkinterdnd2` package is
  present (a "Paste paths…" button covers the same job without
  it); "Open in player" / ▶ plays a preview row's file read-only;
  Android opens CSVs shared or opened from other apps (the file is
  copied into app storage and layered from the copy).

## 1.4.0 — 2026-10-15

* **Append export (desktop 1.3.0 + Android app 1.1.0)** — library
  exports can now *merge* into an existing CSV instead of replacing
  it, so one library CSV can be built up folder by folder: export
  one folder, then append scans of other folders into the same
  file. Rows are keyed by `FilePath`; a re-scanned file's row
  updates in place (same position, fresh values, only for the
  columns the scan produces — hand-added columns and their values
  survive), rows outside the scan are kept untouched, new files
  append at the end, and new tag columns are added at the end of
  the header. If the target CSV has no `FilePath` column, rows fall
  back to keying on the file-name column with a clear warning.
  Desktop: `export --append` on the CLI plus "Append to an existing
  CSV…" in the Export dialog, with an added/updated/kept summary.
  Android: "Append to existing CSV" in the Export dialog (SAF
  picker), same merge rules and summary; the app's export now also
  writes the `FilePath` column (path relative to the picked folder)
  that the merge keys on.

## 1.3.0 — 2026-10-15

* **Android app (v1.0.0)** — a native Kotlin companion ships in
  `android/`, released as `MP3CsvTagger-v1.0.0.apk`. Same CSV format,
  roles, matching and layering as the desktop program: SAF folder
  picking, per-column Match/Write/Skip roles, filename-pattern layers,
  preview with candidate choice, apply with the shared change-log
  format, tag-snapshot undo (no file copies), export tags to CSV, and
  an extensive built-in Help screen (also in docs/ANDROID_HELP.md).
  The engine is JVM-tested against the same scenarios as the desktop
  suite. Feature parity items are tracked in ROADMAP.md.

## 1.2.0 — 2026-10-15

* **Undo (tag snapshots)** — every Apply now writes a
  `mp3tag_*.undo` snapshot next to the change log holding the tags it
  replaced (never copies of the audio). `mp3csvtagger undo` / the
  Apply tab's "Undo a run…" restores them; files changed since the
  run are skipped unless forced.
* **Export library → CSV** — one row per file, one column per tag,
  plus FileName/FilePath/Folder. The location columns work as Match
  columns in any CSV (and can never be written — files are never
  renamed or moved).
* **Tags from filenames & paths** — `{Tag}` patterns capture values
  from names and folder layouts into a normal, undoable preview
  (GUI dialog + `from-filename` CLI).
* **Library report** — duplicate tracks and spelling variants
  (e.g. `Beatles` vs `beatles`); pick the spelling to keep and the
  fix is built as a preview. Nothing changes automatically.
* **Role presets** — saved column-role setups (JSON in
  `~/.mp3csvtagger/presets/`) plus two built-ins; CSV tab controls,
  `add-csv --preset`, `presets` command.
* **Cover art & lyrics** — a `Cover Art` Write column embeds front
  covers from image paths (blank cell removes art, previewed and
  undoable); lyrics write correctly as USLT (a frame-construction
  bug that stored a list repr for string-text frames is fixed).
* **MusicBrainz fill (opt-in)** — fills only EMPTY Album / Year /
  Recording Date / Genre for files with Title + Lead Performer, at
  1 request/second, into the preview. Offline = clear error, no
  partial writes.
* **Help** — the in-app Help tab is now a 20-topic browser; the same
  text ships as `docs/HELP.md` (generated from `helptext.py`).
* Repository tidy-up: legacy material removed; the docs now describe
  the current program only.

## 1.0.0 — 2026-10-15

First public release.

* Bulk MP3 tagging from CSV files: Match/Write/Skip column roles,
  layered CSVs, case/punctuation-insensitive matching, unknown headings
  as TXXX custom tags, projects, and the `mp3tag_*.log.csv` change log.
* Engine: hash-index matching, in-memory preview, parallel scanning,
  open-and-save-once applying. 600 files × a 600-row CSV preview in
  about a second.
* Desktop GUI (Tkinter) and a full CLI (`run`, project commands).
* Projects are readable JSON (`.mp3p.json`).
* Friendly-name map covers the common frames (and remains editable).
* No crash on MP3s without an ID3 header, ragged CSV rows tolerated,
  unchanged tags not rewritten.
* Standalone Windows build via PyInstaller (`build_windows.bat`).
