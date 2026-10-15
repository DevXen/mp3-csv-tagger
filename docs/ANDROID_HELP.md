> This document is the Android app's built-in Help screen, word for word
> (source of truth: `android/app/src/main/assets/help.md`).

# MP3 CSV Tagger — Help

Bulk-edit the ID3 tags inside your MP3 files, driven by CSV spreadsheets.
You always see a full preview before anything is written, every Apply run
saves a change log, and every run can be undone from a tag snapshot —
no file copies, ever.

Contents: Getting started · Picking a folder and CSVs · Roles ·
Layered CSVs · Filename patterns · Matching rules · Preview and
choosing values · Apply, backups and undo · Export tags to CSV ·
The change log · Troubleshooting · FAQ

---

## Getting started

The whole workflow is four steps:

1. **Pick your music folder.** Everything in it (including subfolders)
   is scanned for MP3 files.
2. **Add a CSV file** and tell the app what each column means by giving
   it a role: Match, Write or Skip. One CSV is enough — most jobs need
   exactly one.
3. **Build the preview.** You see every file that matches and exactly
   what would change, old value → new value.
4. **Apply.** The tags are written, a change log is saved, and a tag
   snapshot is taken first so the run can be undone.

Nothing about your files changes until step 4, and nothing is ever
renamed or moved: file names and folder names can be a *source* of tag
values (see Filename patterns), never a target.

The app has no account, no network access and no analytics. Everything
happens on your phone, in the folders you pick.

## Picking a folder and CSVs

**Music folder.** Tap "Pick music folder" and choose the folder that
holds your MP3s. The picker is Android's standard folder picker (the
Storage Access Framework): you choose once, the app remembers the grant,
and it can read and write the MP3s inside that folder — and only there.
Subfolders are included automatically, which is how the app knows each
file's folder path for filename patterns.

If you later move the folder or revoke access in Android settings, just
pick the folder again.

**CSV files.** Tap "Add CSV file" for each spreadsheet you want to use.
A CSV is a plain text file: first row is the column headings, each
following row is a set of values. Files exported from Excel, LibreOffice
or Google Sheets (File → Download → CSV) work as-is; UTF-8 with or
without a BOM is fine.

CSV files are *layers*. The list order matters: layers run top to
bottom. You can:

- **switch a layer off** with its tick box without removing it,
- **move a layer up or down** to change the order,
- **remove a layer** from the list (the file itself is not deleted),
- **set the role of each column** — tap the layer, then tap a column to
  cycle its role, or use the Match/Write/Skip buttons.

Your layer list, roles and order are remembered between sessions.

## Roles

Every column of every CSV has one role:

- **Match** — the row only applies to files whose current value for this
  column equals the row's value. This is how a row finds "its" files.
- **Write** — the row's value is written into matched files for this
  column.
- **Skip** — the column is ignored in this layer. New columns always
  start as Skip, so adding a CSV never changes anything until you say so.

Column headings are tag names. A heading can be:

- an ID3 frame id: `TIT2`, `TPE1`, `TCON`, …
- a friendly name: `Title`, `Lead Performer`, `Artist`, `Album`,
  `Genre`, `Year`, `Track Number`, `Composer`, `Comment`, `Lyrics`, …
- **any other name you like** — it becomes a custom field (an ID3 TXXX
  tag) named exactly that: `Subgenre`, `Rating`, `Mood`, `Catalogue No`.
  Custom fields work both ways: write them now, match on them later.

A useful layer needs at least one Write column. With no Match columns,
every row applies to every file — handy for blanket fixes ("set Genre
to Rock for this whole folder"), dangerous if it's not what you meant,
which is why the preview exists.

## Layered CSVs

One CSV is enough for most jobs. Layers earn their keep when one fix
depends on another:

- Layer 1 matches on Lead Performer and writes Genre = "Rap Metal".
- Layer 2 matches on Genre = "Rap Metal" and writes Rating = 5.

Layer 2 can match on the value layer 1 *writes*, even though no file on
disk has that value yet — after each layer, its chosen values become
the files' effective values for the next layer. Within the preview this
is all shown before anything is written.

When two layers (or two rows) offer *different* values for the same tag
on the same file, both are kept as candidates, the later layer wins by
default, and you can pick the other one in the preview.

## Filename patterns

Your files already carry information in their names and folders —
`Rage Against the Machine/Greatest Hits/09 - Township Rebellion.mp3`.
A filename-pattern layer turns that into tags instead of typing it into
a spreadsheet.

Add one with "Add filename pattern" and write a pattern with `/`
between folder levels and `{Tag Name}` placeholders for the parts you
want to capture:

```
{Artist}/{Album}/{Track} - {Title}
```

- The last segment matches the file name (without `.mp3`).
- Text outside `{…}` must match literally (case does not matter).
- If your folders nest deeper than the pattern, the pattern anchors to
  the end of the path: `{Album}/{Title}` happily matches
  `Music/Rock/Greatest Hits/Anthem.mp3`.
- Captures become Write values for that file. A file whose path does
  not match the pattern's literals is simply left out.
- Patterns are layers: they sit in the same list as CSVs, run in order,
  and later CSV layers can match on the values a pattern wrote.

## Matching rules

A row applies to a file only when **all** of its Match columns equal the
file's current values — after both sides are normalised: trimmed,
lower-cased, and stripped of all punctuation. So:

- file `Don't Stop!` matches CSV `dont stop`
- file `Rage Against the Machine` matches CSV `rage against the machine`
- file `AC/DC` matches CSV `ACDC`
- file `The Beatles` does **not** match CSV `Beatles` — different words
  are different values, always.

There is no fuzzy matching. If a row doesn't apply, the reason is always
visible: build the preview and check the file's current values against
the row, character by character after punctuation is removed.

## Preview and choosing values

"Build Preview" scans the folder, reads every file's tags, and works
out the changes. For each matched file you see one line per Write tag:

```
Genre: Rock → Rap Metal
```

- A tag whose new value equals the old one is not a change and won't be
  written.
- A cell showing "(2 values)" means two rows or layers offered values.
  Tap it to see each candidate with the CSV and row it came from, and
  pick the one you want. The later layer's value is pre-selected.
- Files that could not be read are listed as scan errors at the top —
  one bad file never stops the run.
- "Export preview CSV" saves the preview itself as a spreadsheet:
  file, tag, old value, new value, whether it changes, and where the
  value came from. Useful for reviewing a big run on a computer first.

Rebuilding the preview after editing roles or layers is instant enough
that the intended rhythm is: tweak, preview, look, tweak again, and
only Apply when the preview is exactly right.

## Apply, backups and undo

**Apply** writes the preview's chosen values. For each file that
actually changes, the app opens it once, writes all of its tags in one
save, and moves on. Frames you are not changing — including cover art —
are preserved.

Before the first file is touched, the app creates a **run folder** in
its own storage (shown on the result screen, and kept until you delete
it from a file manager) containing:

- the **change log** CSV (see below), and
- an **undo file (tag snapshot)**.

### Undo (tag snapshot — no file copies)

Undo does **not** copy your MP3s. Copying a library to back it up would
take forever and gigabytes of space, to protect a few kilobytes of tags.
Instead, the snapshot stores only the tag data of each changed file:
the raw bytes of every ID3 frame except cover art (APIC) and private
frames (PRIV). Undo then:

1. writes the snapshot's tags back,
2. streams the file's current audio after them — the audio bytes are
   never modified by a run or by an undo,
3. and for a file that had **no ID3 header** before the run, removes
   the header entirely, restoring its exact original state.

Safety rails: undo checks each file's size and modification time
against the snapshot. A file that changed since the run (replaced,
edited by another app) is **skipped with a warning**, because its audio
may no longer be the audio the snapshot belongs to. You can force the
restore for skipped files if you know the change was harmless.

The one exception to "tags only": if a future version ever edits cover
art, the old artwork of *those files only* is included in their
snapshot. Nothing in this version edits cover art.

To undo: on the main screen, "Undo last run". Only the most recent run
is offered there; older run folders keep their snapshots too, but
restoring from them is a deliberate manual step for now.

## Export tags to CSV

"Export tags to CSV" writes a spreadsheet of your library as it is now:
one row per MP3, a File column, then one column per tag name found
anywhere in the folder. Two good uses:

- **A backup you can read** — a human-friendly record of your tags.
- **An editing round-trip** — export, fix values in a spreadsheet,
  save as CSV, add it as a layer with roles (match on File? no — match
  on a tag like Title or a custom field), preview, apply. The export is
  deliberately in the same format the app reads.

Export includes custom (TXXX) fields under their own names, so nothing
you have tagged is lost in the round-trip.

## The change log

Every Apply run writes `mp3tag_YYYYMMDD_HHMMSS.log.csv` into its run
folder, with one row per tag written:

```
Timestamp, File, Tag Name, ID3 Frame, Original/Old Value, New Value
2026/10/15 11:04:22, 01 Township Rebellion.mp3, Genre, TCON, Rock, Rap Metal
```

Keep these. They are the permanent, readable record of what every run
changed — the thing you (or a script) would work from to reverse a run
by hand long after the fact. The desktop version of MP3 CSV Tagger
writes exactly the same format, so logs mean the same thing everywhere.

## Troubleshooting

**A row matches nothing.** Check the Match values against the file's
current tags exactly (Export tags to CSV shows them). Remember:
punctuation and case are ignored, words are not — and watch for extra
spaces inside spreadsheet cells.

**A file shows no tags / wrong tags.** It may carry ID3v1-only tags or
an unusual header. Export shows what the app sees; files it cannot parse
at all appear as scan errors in the preview.

**"Permission" or the folder stopped working.** Android sometimes drops
folder grants after a reboot, a move, or an app update on some devices.
Pick the folder again; your layers and roles are kept.

**Apply reports a write error for one file.** The file may be on
read-only storage, inside a folder the grant doesn't cover for writing,
or genuinely corrupt. The run continues past it and the result screen
lists it. Fix access and re-run — files already written are unchanged
by a second preview because their values now match.

**Undo skipped my file.** Its size or modification time changed since
the run — usually another app (a player writing play counts or art)
touched it. If you're sure the audio is the same, use Force in the
undo dialog.

**The CSV looks right but columns are missing.** The first row must be
the headings. A file whose first row is data will treat that row as
headings; re-export from your spreadsheet with headers.

**Everything is slow.** A preview reads only the tag block at the start
of each file, so even big folders scan quickly. Apply speed is bounded
by your storage: each changed file is rewritten once, through Android's
document layer — SD cards are slower than internal storage.

## FAQ

**Does it rename or move files?** Never. File and folder names are only
ever read — as a source for tag values via filename patterns.

**Does it change my audio?** No. Tag writing rewrites the tag block at
the start of the file; the audio frames after it are copied through
untouched, byte for byte.

**What about cover art?** Untouched. Artwork is preserved on every
write and excluded from tag snapshots (it's the one frame that can be
megabytes).

**FLAC / M4A / other formats?** Not in this version — MP3/ID3 only,
same as the desktop program.

**Do my CSVs and library need to be on the phone?** The folder you pick
can be internal storage or an SD card — anything Android's picker can
reach. CSVs can live anywhere pickable.

**Is anything uploaded anywhere?** No. The app has no network
permission at all.

**Can I use the same CSVs and logs as the desktop version?** Yes — the
formats are shared on purpose, and a change log from either app reads
the same in a spreadsheet.

**What does the app store about me?** Only your picks: the folder and
CSV grants, layer order and roles, kept on the phone so reopening the
app picks up where you left off.
