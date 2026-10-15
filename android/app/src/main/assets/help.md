# MP3 CSV Tagger — Help

Bulk-edit the ID3 tags inside your MP3 files, driven by CSV spreadsheets.
You always see a full preview before anything is written, every Apply run
saves a change log, and every run can be undone from a tag snapshot —
no file copies, ever.

Contents: Getting started · Picking a folder and CSVs · Roles ·
Layered CSVs · Filename patterns · Matching rules · Preview and
choosing values · Editing a value by hand · Apply, backups and undo ·
Export tags to CSV · Syncing tags from another folder · Consistency
check · Library report · Jobs · Opening a CSV from another app ·
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
- **Every** cell can be tapped, not just multi-value ones — see
  "Editing a value by hand" below.
- The **Group by album** checkbox rearranges the preview under album
  headings (album name, or the file's top folder when it has no album
  tag) so you can review one album at a time. Display only.
- Tap the **▶** button on a file's header line — or long-press the
  header — to play the file in your usual player and hear what you
  are about to tag. Playing only reads the file.
- Files that could not be read are listed as scan errors at the top —
  one bad file never stops the run.
- "Export preview CSV" saves the preview itself as a spreadsheet:
  file, tag, old value, new value, whether it changes, and where the
  value came from. Useful for reviewing a big run on a computer first.

Rebuilding the preview after editing roles or layers is instant enough
that the intended rhythm is: tweak, preview, look, tweak again, and
only Apply when the preview is exactly right.

## Editing a value by hand

Sometimes one value in the preview is simply wrong and editing the
CSV for a single cell is overkill. Tap the cell:

- The dialog lists the candidates (tap one to choose it, as before)
  and offers a text field with the current value. Type the correction
  and save it as a **manual edit**.
- A manual edit outranks every CSV candidate for that cell. It is
  drawn bold, marked "✎ manual edit", and the change log records
  "manual edit" as its source, so hand edits are always
  distinguishable from CSV-driven changes.
- Apply writes manual edits exactly like CSV values, and the undo
  snapshot covers them like everything else.
- To take an edit back, tap the cell again and use **Revert edit**:
  the manual value is removed and the cell falls back to its
  selected candidate.
- Typing back exactly the value already in the file cancels the
  change for that cell.

Manual edits live in the preview, not in any CSV. Rebuilding the
preview discards them — apply first, or expect to redo them.

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

The one exception to "tags only": when a run changes a file's cover
art — which only tag sync does, and only when you ask it to — the old
artwork of *those files only* is included in their snapshot, so
undoing a cover change restores the old picture.

To undo: on the main screen, "Undo last run". Only the most recent run
is offered there; older run folders keep their snapshots too, but
restoring from them is a deliberate manual step for now.

## Export tags to CSV

"Export tags to CSV" writes a spreadsheet of your library as it is now:
one row per MP3, a File column and a FilePath column (the file's path
inside the picked folder), then one column per tag name found anywhere
in the folder. Two good uses:

- **A backup you can read** — a human-friendly record of your tags.
- **An editing round-trip** — export, fix values in a spreadsheet,
  save as CSV, add it as a layer with roles (match on File? no — match
  on a tag like Title or a custom field), preview, apply. The export is
  deliberately in the same format the app reads.

Export includes custom (TXXX) fields under their own names, so nothing
you have tagged is lost in the round-trip.

**Building one CSV folder by folder (append export).** A library
rarely lives in one folder. Export the first folder as a new CSV,
pick the next folder, then choose "Append to existing CSV" and pick
that same CSV file: the new scan is merged into it.

- Rows are matched by the FilePath column. A file already in the CSV
  gets its row updated in place; new files are added at the end.
- Rows for files that were not in this scan are kept exactly as they
  are — appending never removes anything.
- Tag columns the new scan introduces are added at the end of the
  header. A column the scan does not produce — including one you
  added by hand — keeps its existing values.
- Afterwards the app reports how many rows were added, updated and
  kept, and which columns were added.

If the CSV has no FilePath column, rows are matched by file name
instead and the app warns you — names are weaker, because two
different files can share a name.

## Syncing tags from another folder

If the same music lives in two places — this phone's copy and a
master library elsewhere — the tags only have to be right in one of
them. "Sync tags from another folder…" copies tag values from a
source folder into the folder you have picked:

- Files are paired by their path inside each folder, compared
  case-insensitively: `<source>/Rock/ABBA/Gold/01.mp3` pairs with
  `<your folder>/Rock/ABBA/Gold/01.mp3`. Files present on only one
  side are counted and listed — and never touched.
- You choose which tags to copy, and whether cover art copies too. A
  tag copies only when the source has a value and yours differs — an
  empty source value can never blank out your tags — and a cover
  copies only when the two covers actually differ.
- The result is an ordinary preview (its values show the source
  "tag sync"): review it, Apply it, undo it like any other run.

Nothing is copied file-wise — sync moves tag values, not audio.

## Consistency check

Your folders and file names follow your own convention, which makes
them a useful lie detector for the tags. "Consistency check…" takes
a filename pattern — the same `{Tag}` patterns as filename-pattern
layers, for example `{Artist}/{Album}/{Track} - {Title}` — and
compares the value each file's path implies against the tag actually
stored in the file. Case and punctuation differences are ignored,
exactly like matching.

The result is a list of disagreements (file, tag, what the path says,
what the tags say) plus the files whose names do not fit the pattern
at all. **It is read-only**: there is no way to write anything from
this screen. Share the findings with the Share button if you want
them elsewhere; fix genuine errors afterwards with a CSV, a
filename-pattern layer, a manual edit, or a sync — your choice.

## Library report

"Library report…" analyses the picked folder without changing
anything:

- **Album completeness** — per album, how many tracks have a Title,
  Lead Performer, Album, Year, Genre, Track Number and Cover Art,
  with percentages and a library-wide summary. Files with no album
  tag gather under "(no album)".
- **Duplicates** — groups of files whose Title and Lead Performer
  agree: usually the same song ripped twice.
- **Spelling variants** — values of a tag that are the same after
  normalising but spelled differently in the files ("Beatles" vs
  "beatles"). Different words — "The Beatles" vs "Beatles" — are
  different values, not variants.

"Share report" sends the whole report as text to any app. The
report only reports: if you act on it, the fix is a normal previewed
run, so nothing is ever changed automatically.

## Jobs

A job saves a whole run under a name: the music folder, the layers
with their roles and on/off states, and filename-pattern layers.

- "Save current job…" stores the setup you have right now.
- "Jobs…" lists saved jobs: tap one to load it and build its preview,
  or delete it.
- The most recent jobs (up to four) also appear as **launcher
  shortcuts**: long-press the app icon and pick a job to open the app
  straight into that job's preview. Applying is still a separate,
  deliberate step.

Jobs are stored on the phone, in the app's own storage.

## Opening a CSV from another app

The app registers as a handler for CSV files: in a file manager,
browser download, or mail/chat attachment, "Open with" → MP3 CSV
Tagger (and the Share sheet works too). The CSV is **copied into the
app's own storage** and added as a layer from that copy — so the
layer keeps working after the original moves or the sending app
closes, and the app never needs permission to the sender's files.
Give the copy's columns their roles as usual.

## The change log

Every Apply run writes `mp3tag_YYYYMMDD_HHMMSS.log.csv` into its run
folder, with one row per tag written:

```
Timestamp, File, Tag Name, ID3 Frame, Original/Old Value, New Value, Source
2026/10/15 11:04:22, 01 Township Rebellion.mp3, Genre, TCON, Rock, Rap Metal, tags.csv
```

Source says where each written value came from: the CSV file's name
for ordinary writes, or the feature that produced it — "manual edit"
for values typed into the preview, "tag sync" for synced values.

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

**What about cover art?** Preserved on every write. CSV layers never
change it; tag sync can copy it from a twin file, only when you tick
the cover box — and then the target file's old artwork is included in
that run's undo snapshot, so the change can be undone like any other.

**Can it identify songs by their sound (fingerprints)?** Not on
Android. The desktop version can match recordings by audio
fingerprint (with the free fpcalc tool) and look them up on
AcoustID. There is no fingerprint library for Android that provably
produces identical fingerprints to the desktop tool — a near-miss
fingerprint would silently fail to match — so the phone app leaves
fingerprinting to the desktop rather than fake it. The app has no
network permission in any case.

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
