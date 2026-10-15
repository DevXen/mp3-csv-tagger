# Android app — assessment and plan

**Status: planned, not built.** The desktop program and CLI in this repo
are the "real program" the 2019 original never quite became; this page is
the honest scope for taking the same workflow to Android, so it can be
picked up as its own piece of work instead of being promised casually.

## Why it is not just a repackage

* Python/mutagen do not ship to Android in any supportable way for a
  public app. The engine would be re-implemented against a native ID3
  library — the standard choice is **jaudiotagger** (the library behind
  most Android tag editors), from Kotlin.
* Android does not give apps free rein over a music folder: the app must
  use the **Storage Access Framework** (the user picks the music folder
  once; the grant persists), and writes go through `DocumentFile`.
  Android 13+ also splits media permissions, which matters for listing
  files the user did not pick through SAF.
* Neither point is hard; both mean the Android app is a **native
  companion that shares the format**, not a port of this Python code.

## What transfers unchanged

* The CSV format, roles (Match/Write/Skip), the normalisation rule, and
  layered CSVs — they are the product; see `docs/CSV_FORMAT.md`.
* The project file: it is plain JSON, so a project made on desktop can be
  opened on the phone as-is.
* The change-log CSV format, so logs mean the same thing everywhere.
* The sample CSVs and the behaviour pinned by `tests/` — the Android
  implementation should be tested against the same fixtures.

## Shape of the app (Kotlin, single module to start)

1. **Pick music folder** (SAF) → list MP3s, read tags with jaudiotagger
   off the main thread (coroutines; the same hash-index matching applies
   verbatim, it is ~50 lines).
2. **Pick CSVs, set roles** — the desktop CSV tab as a phone screen:
   layer list, per-column role chips.
3. **Preview** — list of matched files with old → new; tap a
   multi-candidate tag to choose a value.
4. **Apply** — write via jaudiotagger, save the change log into the
   folder the user picks.
5. No account, no network, no analytics — it is a file tool.

Estimated at a small app (the engine logic is already proven here); the
risks are all platform behaviour (SAF write quirks on some OEM builds,
scoped-storage edge cases for SD cards), which is why it gets its own
testing pass on real devices before release rather than shipping as a
checkbox in this repo.
