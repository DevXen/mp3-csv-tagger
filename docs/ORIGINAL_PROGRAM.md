# The original program — what it was, how it was recovered, why it was slow

## What was uploaded

`mp3_v15_28_a8lb.zip` (May 2019) does **not** contain a Java program, and it
does not contain source code at all. It is the *frozen build* of a Python
program:

* `gui.exe` — a 32-bit **PyInstaller** bundle (Python **3.7**, x86) with the
  application bytecode inside it, plus its runtime DLLs (`python37.dll`,
  `sciter.dll`, `libssl`, `sqlite3`, …).
* `resources.dat` — a zip holding the **Sciter** UI: HTML, CSS and
  TIScript views for the tabs (Files / CSV / Preview / Configuration /
  Apply / About), icons, and `configuration.json`.
* `mp3_log.txt` — a debug log from a run on the developer's machine, which
  names the project layout (`.../fiverr/mp3-tagging/pycharm-project/`) and
  the two test CSVs, `Sample1.csv` / `Sample2.csv`.

Its own About box says it plainly: *"developed using Python 3.7.2, Sciter,
Pysciter, Mutagen and other Python libraries."*

## How the source was recovered

1. The PyInstaller archive inside `gui.exe` was unpacked (its `PYZ` module
   archive lists every module by name — `lib.project`,
   `lib.project.preview`, `lib.util.mp3.tagmanager`, the controllers…).
2. The Python 3.7 bytecode for the application's own `lib` package was
   decompiled with `uncompyle6`. Every module decompiled cleanly.
3. `resources.dat` was unzipped for the UI files, the configuration and
   the log.

The recovered material lives in [`original-recovered/`](../original-recovered/)
as a read-only reference, and the original zip is attached to the GitHub
release as `original-2019-program.zip`. It is not the maintained code —
decompiled code is a *record*, not a code base — but it is how the rewrite
could preserve the original's exact behaviour:

* column roles **Match = 1, Write = 2, Skip = 3**, new columns defaulting to Skip;
* matching by "lower-case, strip punctuation" equality on **all** Match columns;
* CSVs as ordered **layers**, each able to Match on what an earlier layer writes;
* unknown headings stored as **TXXX** custom tags named after the heading,
  with the four seeded friendly names (`TPE1` Lead Performer, `TPE2` Band,
  `TPE3` Conductor, `TPUB` Publisher);
* `PRIV` and `APIC` frames ignored; projects saved to disk; an Apply that
  writes a change log named `mp3tag_YYYYMMDD_HHMMSS.log.csv` with the columns
  `Timestamp, File, Tag Name, ID3 Frame, Original/Old Value, New Value`.

## Why it ran slow

All three causes below are visible in the decompiled code:

1. **A database commit per tag.** The project *and* the preview lived in a
   SQLite database (SQLAlchemy). `add_preview_mp3_tag`, `add_preview`,
   `add_comparison_tag_name` and friends each call `session.commit()` —
   so building a preview for a library meant thousands of individual
   commits, each flushing a transaction.
2. **Rows × files × tags matching, with the normalisation inside.** For
   every CSV row, the preview looped over every candidate file and, per
   tag, lower-cased and punctuation-stripped both the file's value and the
   row's value again. The same values were re-processed thousands of
   times instead of once.
3. **Serial, single-threaded work on a 32-bit interpreter**, through a
   heavyweight UI engine, including re-reading files through per-file
   object wrappers. Add a crash on the first MP3 with no ID3 header
   (mutagen's `ID3()` raises), and big runs were both slow and fragile.

## What the rewrite changed

* Hash-index matching (each value normalised once), in-memory preview,
  parallel scanning, open-and-save-once applying — same rules, modern
  Python 3.10+ 64-bit, one dependency (mutagen), Tkinter instead of Sciter.
* Projects are plain JSON you can read, diff and edit.
* A CLI makes the whole flow scriptable and testable; the behaviour is
  pinned by the test-suite in `tests/`.
* Deliberate fixes: files with no ID3 header no longer kill a run; ragged
  CSV rows are padded instead of crashing the reader; unchanged tags are
  not rewritten unless you ask.

Everything else — roles, layering, matching, the change-log format, the
TXXX convention — is the original design, kept.
