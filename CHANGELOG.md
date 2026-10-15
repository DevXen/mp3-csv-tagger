# Changelog

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
