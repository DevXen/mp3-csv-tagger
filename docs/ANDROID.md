# Android app

**Status: shipped — v1.0.0.** The Android companion lives in
[`android/`](../android/) and ships as the signed APK attached to the
project's GitHub releases (`MP3CsvTagger-v1.0.0.apk`). It is a native
Kotlin app that shares this project's format and rules: same CSV files,
same Match/Write/Skip roles, same matching normalisation, same layered
runs, same change-log format.

## What it does

* **Pick a music folder** with Android's folder picker (SAF). The grant
  persists; MP3s are found recursively. Files are never renamed, moved
  or deleted — names and folder paths are only ever *read*.
* **Tag reading** pulls just the ID3 block at the start of each file, so
  scanning a big folder does not copy it. Files with unusual headers
  fall back to a jaudiotagger read. A file with no ID3 header simply has
  no tags yet — it is not an error.
* **CSV layers** work exactly as on desktop: add one CSV (most jobs need
  exactly one) or several, set each column's role, reorder, switch
  layers off. Layer order, roles and picks are remembered.
* **Filename-pattern layers** derive tags from folder/file names with
  `{Tag}` patterns, e.g. `{Artist}/{Album}/{Track} - {Title}` — the same
  patterns the desktop app uses.
* **Preview** shows old → new for every matched file; where several
  values compete for one tag, tap to choose (the last layer wins by
  default). The preview can be exported as CSV.
* **Apply** writes each changed file once (temp copy → jaudiotagger →
  written back through SAF), preserving cover art and every frame it
  does not touch. A run folder keeps the change log
  (`mp3tag_YYYYMMDD_HHMMSS.log.csv`, the shared format) and the undo
  snapshot.
* **Undo (tag snapshot — no file copies)** stores only the changed
  files' tag frames (cover art and private frames excluded, unless a
  run itself changed a file's cover art). Undo restores those tags,
  removes headers the run created, and skips files whose size or
  modification time changed since the run, with an option to force.
* **Export tags to CSV** — one row per MP3 (File + FilePath columns,
  then one column per tag name): a readable library record, and a
  round-trip editing format. Exports can also **append**: merge a
  scan into an existing library CSV — rows keyed by FilePath,
  re-scanned files update their rows in place, new files and new tag
  columns append at the end — so one library CSV can be built up
  folder by folder, exactly like the desktop program.
* **Help** — an extensive built-in Help screen; the same text is in
  [ANDROID_HELP.md](ANDROID_HELP.md).

No account, no network permission, no analytics. It is a file tool.

## Building

```bash
cd android
./build.sh                 # signed release APK (assembleRelease)
./build.sh testDebugUnitTest
```

The engine (matching, layers, preview, export) is plain Kotlin with no
Android dependencies and is covered by JVM unit tests that pin the same
behaviour as the desktop test-suite, including the tag-snapshot
capture/restore cycle. The release signing key lives outside the repo;
a clone without it builds with the debug key (the build file says so).

## Not in the Android v1

Feature parity is a direction, not a claim. The desktop app's role
presets, library report (duplicates / spelling variants), cover-art
column and MusicBrainz fill are not in the Android v1 — see
[ROADMAP.md](../ROADMAP.md). The phone is also the honest proof gate
for SAF behaviour across devices: the APK is build- and test-verified,
and real-device behaviour is confirmed by using it.
