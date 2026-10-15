# Changelog

## 1.0.0 — 2026-10-15

The rewrite release.

* Clean-room reimplementation of the 2019 MP3 File Tagging program
  (Python 3.7 / Sciter / PyInstaller 32-bit), recovered by decompiling the
  shipped `gui.exe` — see `docs/ORIGINAL_PROGRAM.md` and
  `original-recovered/`.
* Same workflow and rules: Match/Write/Skip column roles, layered CSVs,
  case/punctuation-insensitive matching, unknown headings as TXXX custom
  tags, projects, and the `mp3tag_*.log.csv` change log.
* New engine: hash-index matching, in-memory preview, parallel scanning,
  open-and-save-once applying. 600 files × a 600-row CSV preview in
  about a second.
* New: a full CLI (`run`, project commands) — the original was GUI-only.
* New: projects are readable JSON (`.mp3p.json`) instead of a copied
  SQLite database.
* New: friendly-name map covers the common frames (and remains editable).
* Fixes kept from the post-mortem: no crash on MP3s without an ID3
  header, ragged CSV rows tolerated, unchanged tags not rewritten.
* Standalone Windows build via PyInstaller (`build_windows.bat`);
  Android companion scoped in `docs/ANDROID.md`.
