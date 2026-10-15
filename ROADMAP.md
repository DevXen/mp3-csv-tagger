# Roadmap

Ideas for MP3 CSV Tagger, roughly in the order they are likely to be
picked up. Nothing here is a promise or a date — it is the shared
parking lot for "that would make this better", kept next to the code
so suggestions survive between sessions.

## Android parity (the desktop app has these today)

* **Role presets** — bring the desktop's saved column-role presets
  (including the two built-ins) to the Android layer editor, in the
  same JSON format so presets can move between phone and desktop.
* **Library report** — duplicate tracks and spelling-variant finder
  (e.g. `Beatles` vs `beatles`) with the same rule: the user picks the
  spelling to keep, the fix is built as a normal preview.
* **Cover art column** — embed or remove front covers from image paths,
  with the snapshot rule already in place (a file whose cover changes
  gets its old APIC included in that run's undo snapshot).
* **MusicBrainz fill (opt-in)** — fill only empty Album / Year /
  Recording Date / Genre, at the same polite rate, into the preview.
  This would be the Android app's first network feature and stays
  strictly opt-in, off by default.
* **Older undo runs** — browse past run folders and restore from any
  snapshot, not just the most recent run.

## Both platforms

* **Undo on desktop for Android runs and vice versa** — the snapshot
  and change-log formats are deliberately shared already; a small
  "restore from snapshot file" entry point on each side would close
  the loop.
* **More filename-pattern power** — optional segments and multiple
  patterns tried in order for mixed library layouts.
* **Larger-library performance passes** — the engines are built around
  hash indexes and one-pass scans; profile with a 50k-file library and
  publish the numbers before optimising anything.

## Deliberately out of scope

* **File renaming and folder reorganisation.** File and folder names
  are a *source* of tag values (filename patterns), never a target.
  The media libraries this tool serves follow their owner's naming
  convention, and the tool will not impose another one.
* **Automatic text "cleanup" transforms.** No silent trimming,
  re-casing or suffix-stripping of tag values. Matching is forgiving
  (case and punctuation are ignored when comparing); writing is exact:
  the value in the CSV or pattern is the value that lands in the file.
  Anything else would be the tool editing the user's data on its own
  initiative.
* **Accounts, sync and analytics.** Both apps are local file tools.
