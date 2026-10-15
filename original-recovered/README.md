# Recovered original (2019) — reference only

This folder preserves what was recovered from the uploaded
`mp3_v15_28_a8lb.zip` on 2026-10-15. **It is not maintained code** — the
program that is developed and released lives in `src/mp3csvtagger/`.
This is kept so the rewrite's behaviour can be checked against the
original, and so the original work is not lost.

* `gui-main.py` — the decompiled entry point (`gui.exe`'s main script:
  it just starts `lib.gui.gui`).
* `decompiled-lib/` — the application's `lib` package, decompiled from
  Python 3.7 bytecode with uncompyle6: controllers, project/preview
  engine (SQLAlchemy + SQLite), CSV and MP3 utilities, Sciter plumbing.
  Decompiler banner comments at the top of each file name the original
  source path.
* `resources/` — the Sciter UI extracted from `resources.dat`: HTML/CSS/
  TIScript views for every tab, `configuration.json` (default colours,
  the four seeded tag names, the developer's local test paths), and the
  Icons8 icon set the UI used.

The original binaries themselves (`gui.exe` and its 2019 DLLs) are
attached to the GitHub release as `original-2019-program.zip` — the
exact zip that was uploaded — rather than committed to git.
See `../docs/ORIGINAL_PROGRAM.md` for the full recovery write-up.
