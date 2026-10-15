# Help — MP3 CSV Tagger

The full in-app help text. Generated from `src/mp3csvtagger/helptext.py` — edit it there.

## Getting started

MP3 CSV Tagger edits the ID3 tags inside MP3 files, driven by CSV
spreadsheets. Instead of opening files one by one, you describe the
changes once — "every track whose Artist is X gets Genre Y" — and the
program applies them to your whole library, with a preview first.

The five steps, which are also the first five tabs:

  1. Files   — tell it which MP3 files or folders to work on.
  2. CSV     — add one or more CSV files and give each column a role.
  3. Preview — see exactly which files match and what would change.
  4. Apply   — write the changes, and get a change log.
  5. Setup   — optional: rename how tag frames are displayed.

Nothing is ever written to a file before Apply, and Apply only writes
what the Preview showed. If you are new, do a first run on a small test
folder — the Examples folder in the source repository builds a
three-track sample library for exactly that.

You do NOT need two CSV files. One CSV is enough for most jobs; several
CSVs are an advanced option ("Layered CSV files" topic) for when your
data comes from more than one source.

## Files: choosing your MP3s

Add Folder adds a folder and everything under it (the scan is
recursive). Add File adds individual MP3 files. Both can be mixed, and
adding the same file twice is harmless — it is only scanned once.

Notes:

- The list shows the paths you added, not every file found; the real
  file list is resolved when you build a preview.
- Remove Selected takes paths back off the list. It never deletes
  anything from disk.
- Files that cannot be read (corrupt, not really MP3s) are reported in
  the preview header instead of stopping the run.
- An MP3 with no ID3 tag header at all is fine: it starts with no tags,
  it can still be matched if a CSV row applies to every file, and Apply
  creates the header when it writes.
- Scanning is parallel and fast — thousands of files take seconds. If a
  folder is on a slow network drive, the scan may take longer than the
  rest of the run put together; that is the disk, not the program.

## CSV files and column roles

A CSV file is a spreadsheet: the first row names the columns, each
following row is one set of values. Save from Excel, LibreOffice or
Google Sheets as "CSV (comma delimited)", UTF-8 if asked.

Every column of every CSV gets one role:

  Match — a row only applies to a file when the file's current value
          for this column EQUALS the row's value (see "Matching rules").
  Write — the row's value REPLACES the file's value for this column.
  Skip  — the column is ignored. New columns always start as Skip, so
          adding a CSV can never change anything until you say so.

To change a role in the GUI: select the CSV, then double-click a
column's role to cycle Match -> Write -> Skip, or use the three role
buttons under the column list.

A useful CSV needs at least one Write column. One Match column is
typical; zero Match columns means "every row applies to every file"
(allowed, and right for blanket fixes); several Match columns means a
row only applies when ALL of them match.

Example — one CSV is all this job needs:

  Lead Performer,Genre
  Rage Against the Machine,Rap Metal

with Lead Performer = Match and Genre = Write, sets that genre on
every track by that performer.

## Pseudo-columns: FileName, FilePath, Folder

Three special column headings describe where a file LIVES instead of a
tag inside it:

  FileName — e.g. "01 Township Rebellion.mp3"
  FilePath — the full path of the file
  Folder   — the folder containing the file

They are most useful as Match columns. Because every file's name is
different, a CSV exported from the library (see "Exporting your
library to CSV") can be edited in a spreadsheet and fed back with
FileName or FilePath as the Match column, and every row lands on
exactly its own file — no ambiguity, ever.

Pseudo-columns can only Match, never Write: writing to them would mean
renaming or moving files, and this program never renames or moves your
files. Your naming convention is yours; names are something the
program reads, not something it changes. (A Write role on a
pseudo-column is rejected with an error when the preview is built.)

Matching on pseudo-columns uses the same cleanup as tags (case and
punctuation ignored), so "01 township rebellion.mp3" matches too.

## One CSV or many? Layered CSV files

You only ever NEED one CSV file. Multiple CSVs exist because real data
often comes from several places — one export from a store, one from a
label, your own corrections sheet — and because layering is powerful:

- CSVs run in list order (top first). Use the arrows on the CSV tab to
  reorder them, and the "Included in run" tick box to switch one off
  without removing it.
- A later CSV sees the values earlier CSVs are going to write. So CSV 1
  can normalise genres, and CSV 2 can match on the normalised genre to
  add ratings, comments or custom fields.
- If two layers write the same tag on the same file, both values are
  kept as candidates in the preview. The LAST layer's value is selected
  by default; you can pick the other one (see "Preview in depth").
- Roles are per CSV file. The same column name can be a Write in one
  CSV and a Match in the next — that is exactly how the layering trick
  above works.

The sample files in the Examples folder (Sample1.csv, Sample2.csv)
demonstrate the two-layer pattern, but each of them also works on its
own with the right roles.

## Matching rules

A row matches a file when, for EVERY Match column, the file's current
value and the row's value compare equal after this cleanup:

  - surrounding whitespace is trimmed,
  - everything is lower-cased,
  - all punctuation is deleted.

So these all match each other:

  Don't Stop!   /   dont stop   /   DONT STOP

and these do not:

  The Beatles   vs   Beatles        (different words)
  Track 01      vs   Track 1        (different numbers)

Matching uses the file's value AS IT WILL BE after earlier CSV layers
have written (see "Layered CSV files"). Within one CSV, all matching
uses the values as they were when that CSV started.

Empty matches empty: a row whose Match value is blank matches files
where that tag is blank or missing. That is a deliberate way to find
and fix untagged files.

Matching is exact after cleanup — there is no fuzzy matching. If a run
matches fewer files than you expected, the values genuinely differ:
export a preview CSV and compare them side by side.

## Tag names, frames and custom tags

A CSV column heading is a tag name. It resolves to an ID3 frame — the
thing actually stored in the MP3 — like this:

  1. A frame id works directly: TIT2, TPE1, TCON, TALB, TRCK, ...
  2. A friendly name works too: Title, Album, Genre, Year, Track
     Number, and the aliases Artist (= Lead Performer / TPE1) and
     Band (= TPE2). The full map is on the Setup tab, and you can add,
     edit or remove entries there.
  3. Anything else becomes a CUSTOM tag (a TXXX frame) whose name is
     the heading itself: Subgenre, Rating, Mood, Source, ... Custom
     tags are real tags — other players show them as user-defined
     fields, and this program can Match on them on the next run,
     because the same heading reads the value back.

Two frame types are never treated as text: embedded pictures (APIC)
and private frames (PRIV). Everything else text-shaped — comments,
lyrics, composer, BPM, grouping, copyright — can be matched and
written like any other column.

## Tags from filenames and paths

If your files are named and organised consistently, their names and
folders are a free source of tag values:

  Files tab -> "Tags from filename/path...", or
  mp3csvtagger from-filename --folder ~/Music       --pattern "{Lead Performer} - {Title}"

A pattern is literal text with tag names in braces. The literal text
must match exactly; each {Tag} captures the text up to the next
literal. Examples:

  Name:  "{Lead Performer} - {Title}"
         matches  Rage Against the Machine - Bombtrack.mp3

  Name:  "{Track Number} - {Title}"
         matches  07 - Township Rebellion.mp3   (Track Number = "07")

  Path:  "{Lead Performer}/{Album}/{Track Number} - {Title}"
         (tick "use path"; matched against the path relative to the
         first folder you added, without the .mp3 extension)

Captures are stripped of surrounding spaces. A file whose name does
not fit the pattern is simply skipped. The dialog previews the first
matches live; "Build preview" turns the captures into a normal
preview, which you review and Apply like any other change (undo
snapshot included). Numbers keep their text — "07" stays "07".

Names are only ever READ. This feature never renames a file.

## Role presets

Setting roles column by column gets old when every CSV needs the same
setup. A preset is a saved {column name -> role} map:

  - CSV tab: pick a preset and "Apply preset" to set the roles of the
    selected CSV's columns. Columns the preset does not name keep
    their current roles.
  - "Save roles as preset..." stores the selected CSV's current roles
    under a name you choose. Presets live as plain JSON files in
    ~/.mp3csvtagger/presets/ — copy them between machines, share them,
    or write one by hand.
  - Command line: add-csv --preset "Match artist, write genre", and
    `mp3csvtagger presets` lists what is available.

Two presets ship built in:
  "Match artist, write genre" — Lead Performer and Artist match,
  Genre writes.
  "Fix titles by filename anchor" — FileName matches, Title writes:
  the setup for feeding a hand-edited export back to its own files.

## Preview in depth

Build Preview (Preview tab, toolbar button, or Run menu) scans your
files, matches every CSV, and shows one row per matched file with one
column per Write tag:

  - A cell shows the new value. If it differs from what is in the file
    it shows "old -> new".
  - If several rows or layers offered values for the same tag, the
    cell shows how many values there were. The last layer's value is
    the selected one.
  - Choose value... (with a file row selected) lists every candidate
    with the CSV file and row it came from, and lets you select a
    different one. Your choice is what Apply writes.
  - The header line counts: files scanned, files matched, and total
    tag changes. Files that failed to read are listed there too.
  - Export preview CSV... saves the whole preview — file, tag, frame,
    old value, new value, changed?, candidate count, source CSV and
    row — for checking in a spreadsheet or keeping a record.

A preview is a snapshot. If you edit the CSVs, the roles, or the files
on disk afterwards, build the preview again before applying.

## Cover art and lyrics

Lyrics are an ordinary text tag: a column headed "Lyrics" (or the
frame id USLT) matches and writes like any other.

Cover art is the one non-text column. Head a column "Cover Art":

  - A Write cell holds the PATH of an image file — .jpg, .jpeg or
    .png. Relative paths are resolved against the folder the CSV file
    lives in, so a sheet and its images can travel together.
  - Applying embeds the image as the front cover (picture type 3,
    replacing any existing cover).
  - A BLANK Write cell REMOVES the file's existing cover art. The
    preview shows this as "[remove cover art]" so it is never a
    surprise, and — like every change — it is covered by the undo
    snapshot, which for cover changes includes the old picture.
  - The preview shows an existing cover as "[cover image]" and a new
    one as "[cover image: <file name>]". Image bytes are never loaded
    during scanning or preview, which keeps big libraries fast.

Cover Art cannot be a Match column in any useful sense (there is no
text to compare); use it as Write only.

## Apply, the change log, and undoing a run

Apply writes the preview's selected values:

  - Only files with actual changes are opened, and each is opened and
    saved once, however many tags change in it.
  - Unchanged tags are not rewritten (unless a front-end offers a
    "write unchanged" option and you turn it on).
  - One bad file does not stop the run; failures are reported in the
    output panel with the file name and the error.

Before anything else, Apply writes a CHANGE LOG into the folder set
on the Apply tab (default: a "mp3tagging" folder in your home
directory):

  mp3tag_YYYYMMDD_HHMMSS.log.csv
  Timestamp, File, Tag Name, ID3 Frame, Original/Old Value, New Value

Keep these files. The log is the exact record of what every file used
to say — your audit trail.

UNDO — every Apply that changes at least one file also writes an undo
snapshot next to the log, with the same name stem:

  mp3tag_YYYYMMDD_HHMMSS.undo

The snapshot stores ONLY the tags: for each changed file, every ID3
frame it had before the run (cover art excluded — it is large and a
normal run never touches it; if a run DOES change a file's cover, that
file's old cover is included). Your audio is never copied, so undoing
a 10,000-file run is fast and the snapshot stays small.

To undo a run: Apply tab -> "Undo a run...", or

  mp3csvtagger undo mp3tag_YYYYMMDD_HHMMSS.undo

Undo restores each file's tags to exactly what the snapshot holds. A
file whose size or modification time changed since the run is
SKIPPED and reported — undo never clobbers newer edits. The CLI's
--force overrides that guard when you are sure.

Strong recommendation for big libraries: point the log folder at
somewhere backed up, run on a copied test folder first, and only then
run the real library. The preview is honest, but a backup is a backup.

## Exporting your library to CSV

The workflow also runs backwards, and it is often the best way to
build a tagging CSV in the first place:

  Files tab -> "Export library to CSV...", or
  mp3csvtagger export --folder ~/Music --out library.csv

writes ONE ROW PER FILE with one column per tag found anywhere in the
library, plus three location columns: FileName, FilePath, Folder.
Standard frames appear under their frame ids (TIT2, TPE1, ...); custom
tags under their names.

Edit the export in a spreadsheet — sorting, find-and-replace and
fill-down are much faster there than in any tag editor — then feed it
back as a Write layer. Match on FileName or FilePath (see
"Pseudo-columns") so every row lands back on exactly its own file.

BUILDING ONE CSV FOLDER BY FOLDER (append export)

A library rarely lives in one folder. Instead of one CSV per folder,
export the first folder as above, then APPEND the others into the
same file:

  Files tab -> "Export library to CSV..." -> "Append to an existing
  CSV...", or
  mp3csvtagger export --folder ~/Music/More --out library.csv --append

Append MERGES the new scan into the existing CSV:

  - Rows are matched by FilePath. A file that is already in the CSV
    gets its row updated in place (same position, fresh values);
    files that are new are added at the end.
  - Rows for files that were NOT in this scan are kept exactly as
    they are — appending never removes anything.
  - Tag columns the new scan introduces are added at the end of the
    header (blank for the rows that were already there). A column
    the scan does not produce — including one you added by hand —
    keeps its existing values even on rows that get updated.
  - After an append, the program reports how many rows were added,
    updated and kept, and which columns were added.

One caution: appending needs the FilePath column to match rows
reliably. If it was deleted from the CSV, append falls back to
matching by FileName and warns you — file names alone are weaker,
because two different files can share a name.

(The Preview tab's separate "Export preview CSV..." is different: one
row per pending CHANGE, for reviewing a run before you apply it.)

## Library report: duplicates and spellings

Files tab -> "Library report...", or mp3csvtagger report. Two checks:

DUPLICATES — groups of files whose Title AND Lead Performer agree
(after the usual cleanup). Same song, ripped twice, is the usual find.
The report lists the paths; what you do with them is your call — the
program never deletes files.

SPELLING VARIANTS — for one tag at a time (Lead Performer, Album,
Genre, ...), values that clean up to the same text but are spelled
differently in the files: "Beatles" vs "beatles" vs "BEATLES". (A
difference in actual words — "The Beatles" vs "Beatles" — is a
different VALUE, not a variant, and matching treats it that way too.)

To unify a variant group: select the spelling you want to keep and
press "Use selected spelling". That builds a normal preview changing
every other spelling of the group to the one you picked — review it,
Apply it, and it is undoable like everything else. Nothing is ever
changed automatically: different spellings might be deliberate
(different bands, different releases), and only you know.

"Export report..." saves the findings as a text file, or as CSV
(one row per affected file) if you give the file a .csv name — the
CLI does the same with report --out <file>.

## Filling missing tags from MusicBrainz

Sometimes a file has a Title and an Artist but nothing else. The
MusicBrainz button (Preview tab) / `mp3csvtagger lookup` can fill the
gaps — strictly opt-in:

  - It only fills fields that are EMPTY in the file. Existing values
    are never overwritten, not even offered as changes.
  - You choose the fields: Album, Year, Recording Date, Genre.
  - Files without both a Title and a Lead Performer are skipped —
    there is nothing reliable to search with.
  - Results become ordinary preview candidates (source shown as
    "MusicBrainz lookup"). Review them like any other change; Apply
    writes them, with the usual change log and undo snapshot.
  - Lookup is polite and slow by design: at most one request per
    second (MusicBrainz's rate limit), with this program's name in the
    User-Agent. A big library takes a while; run it on a folder, not
    the whole archive, first.
  - It needs the internet. Offline or a failed search is reported and
    changes nothing — there are no partial writes.

## Projects

A project collects everything a run needs:

  - the MP3 file/folder paths,
  - the CSV files, in layer order, each with its columns' roles and
    its included/excluded state,
  - the friendly tag-name map from the Setup tab,
  - the change-log folder.

Project menu: New, Open, Save, Save As. Project files end in
.mp3p.json and are PLAIN JSON — open one in a text editor and see.
That makes them easy to back up, to version-control, to generate from
a script, and to share with the role setup already done (share the
CSVs it names too; paths inside are your machine's paths).

Tip: one project per library or per job ("Vinyl rips", "Podcast
archive") is easier to manage than one giant project for everything.

## The command line

Everything the GUI does is available headless, for scripts and big
scheduled jobs. The program is `mp3csvtagger`:

  mp3csvtagger                      open the GUI
  mp3csvtagger run --folder ~/Music --csv tags.csv \
      --csv-roles "Lead Performer=Match,Genre=Write" [--apply]
  mp3csvtagger new project.mp3p.json
  mp3csvtagger add-files project.mp3p.json --folder ~/Music
  mp3csvtagger add-csv project.mp3p.json tags.csv \
      --roles "Lead Performer=Match,Genre=Write"
  mp3csvtagger preview project.mp3p.json --out preview.csv
  mp3csvtagger apply project.mp3p.json
  mp3csvtagger undo ~/mp3tagging/mp3tag_20261015_103708.undo
  mp3csvtagger export --folder ~/Music --out library.csv
  mp3csvtagger from-filename --folder ~/Music       --pattern "{Lead Performer} - {Title}" [--apply]
  mp3csvtagger report --folder ~/Music
  mp3csvtagger presets
  mp3csvtagger lookup --folder ~/Music --fields Album,Year,Genre

`run` is a dry run unless you pass --apply. --csv-roles belongs to the
--csv before it: repeat the pair for layered runs where each CSV needs
different roles. Every command has its own --help.

Exit codes: 0 on success, 1 if any file failed to write during apply,
2 for usage errors — so scripts can tell a clean run from a partial
one.

## Troubleshooting

"Fewer files matched than expected"
  The values differ after cleanup (see "Matching rules"). Export the
  preview CSV, and check the Match column values character by
  character — a trailing comment, a featuring-artist suffix, or "The"
  is the usual cause.

"A file was skipped / could not be read"
  The preview header lists read errors. The file may be corrupt, not
  an MP3 despite its name, or open in another program. It is skipped,
  never half-written.

"My custom field does not show in my player"
  Custom (TXXX) tags are stored under their heading name. Players vary:
  most show them as user-defined/custom fields; some hide them. The
  value IS in the file — re-run a preview matching on that heading to
  see it read back.

"The tag I wrote shows the old value in my player"
  Players cache libraries. Rescan/refresh the library in the player,
  or check the file here with a fresh preview.

"Apply failed for one file"
  Usually a read-only file or a file open elsewhere. Fix the cause and
  re-run: matched files that are already correct produce no changes,
  so a second run is safe and quick.

"Everything is slow on a network drive"
  Reading tags means opening every file once. That is disk/network
  time, not matching time — the same run on a local copy is the proof.

## FAQ

Do I need two CSV files?
  No. One CSV with at least one Match and one Write column does most
  jobs. Multiple CSVs are for layered work and multi-source data.

Does it work on FLAC / M4A / OGG?
  No — this program is MP3/ID3 only, by design and by name.

Will it rename or move my files?
  No. It only edits tags inside the files, in place.

Will it overwrite a tag with a blank?
  If a Write column's cell is blank, yes — blank is a value, and the
  preview shows it as an (empty) new value. Delete the row, set the
  column to Skip, or exclude the CSV if that is not what you want.

Can two rows match the same file in one CSV?
  Yes. Both offer their values; the later row in the file is treated
  like the later layer — its value is selected, the other stays
  available in Choose value... .

What happens to my existing tags that no CSV mentions?
  Nothing. Only Write columns are touched; all other frames, pictures
  included, are left exactly as they were.

Is there an undo?
  Yes. Every Apply saves a tag snapshot (an .undo file next to the
  change log); "Undo a run..." on the Apply tab restores the tags of
  that run exactly. No audio is ever copied — see "Apply, the change
  log, and undoing a run". Keep backups of irreplaceable libraries
  regardless — no tag editor is a backup.

Can I clear a tag?
  Yes — a Write column with a blank cell writes blank. For cover art a
  blank cell REMOVES the picture (see "Cover art and lyrics").

## Keyboard and accessibility notes

- Every action is reachable from the menus: Project (New/Open/Save),
  Run (Build Preview / Apply).
- In the CSV column list, double-clicking a role cycles it, which is
  also the fastest way to set up a big CSV with the keyboard and mouse
  together: click a column, double-click its role, move down.
- Text in the Preview, Apply output and Help panes can be selected and
  copied.
- The Help tab is a topic browser: pick a topic on the left, read on
  the right. The same text ships as docs/HELP.md in the source
  repository for reading at full size or printing.
