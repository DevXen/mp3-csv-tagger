# Android app

**Status: shipped — app v1.2.0** (repo release 1.5.0). The Android
companion lives in [`android/`](../android/) and ships as the signed
APK attached to the project's GitHub releases
(`MP3CsvTagger-v1.2.0.apk`). It is a native Kotlin app that shares
this project's format and rules: same CSV files, same
Match/Write/Skip roles, same matching normalisation, same layered
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
  default). **Every cell is tappable**: type a correction as a
  *manual edit* (marked "✎ manual edit", outranks all candidates,
  revertible), group rows by album with the **Group by album**
  checkbox, and play a file from its header row (▶ or long-press,
  read-only). The preview can be exported as CSV.
* **Apply** writes each changed file once (temp copy → jaudiotagger →
  written back through SAF), preserving cover art and every frame it
  does not touch. A run folder keeps the change log
  (`mp3tag_YYYYMMDD_HHMMSS.log.csv`, the shared format — now with the
  trailing Source column, "manual edit" / "tag sync" included) and
  the undo snapshot.
* **Sync tags from another folder** — pair this folder's files with
  a source folder's by relative path and copy the tags you choose
  (cover art too, if you tick it — provably-different covers only).
  Unpaired files are listed and never touched; the result is a
  normal preview.
* **Consistency check** — read-only: compare stored tags against
  the values a `{Tag}` pattern captures from each file's path and
  list the disagreements. No write path exists from this screen.
* **Library report** — album completeness (per album: Title, Lead
  Performer, Album, Year, Genre, Track Number, Cover Art), duplicate
  tracks and spelling variants, shareable as text. Read-only.
* **Jobs** — save a whole setup (folder, layers + roles, patterns)
  under a name, rerun it from the Jobs list, or launch it from a
  home-screen shortcut (long-press the app icon).
* **Open-with / share import** — the app handles CSV files opened
  from other apps; the file is copied into app storage and added as
  a layer from the copy, so the layer survives the sender closing.
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

## Not in the Android app (yet)

Feature parity is a direction, not a claim. Still desktop-only: role
presets, the cover-art CSV column (sync can copy covers between twin
files, but a CSV column of image paths is not wired up), MusicBrainz
fill, and fingerprint matching — the last one has a specific reason,
recorded at the top of [ROADMAP.md](../ROADMAP.md). The phone is also
the honest proof gate for SAF behaviour across devices: the APK is
build- and test-verified, and real-device behaviour is confirmed by
using it.
