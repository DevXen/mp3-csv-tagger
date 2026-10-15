# User Guide

MP3 CSV Tagger edits the ID3 tags inside MP3 files, driven by CSV
spreadsheets. You never edit a file before you have seen a preview of the
change, and every run writes a change log.

## The workflow

### 1. Files

**Files tab → Add Folder / Add File.** Add everything you might tag —
scanning is fast and untagged files simply will not match anything.
Remove paths with *Remove Selected*. A path can be a whole folder
(scanned recursively) or a single file; the actual list of MP3s is
resolved when you build the preview.

### 2. CSV files and column roles

**CSV tab → Add CSV File.** Each CSV you add appears in the list, in
order. Select it to see its columns, and give each column a role
(double-click cycles, or use the Match/Write/Skip buttons):

| Role  | Meaning |
|-------|---------|
| Match | A row only applies to a file when the file's current value for this column **equals** the row's value. Comparison ignores case and punctuation. |
| Write | The row's value is written into the file for this column. |
| Skip  | The column is ignored in this CSV. New columns start as Skip. |

Useful mappings need at least one Match column (otherwise a row would
apply to *every* file — allowed, and sometimes exactly what you want for
blanket fixes) and at least one Write column.

The tick box **Included in run** switches a CSV off without removing it.
The arrows change the **layer order**: CSVs apply top to bottom, and a
later CSV sees the values earlier CSVs wrote (so it can Match on them).
If a heading changes in the file on disk, *Refresh columns from file*
re-reads it and keeps the roles of columns that are still there.

### 3. Preview

**Preview tab → Build Preview** (or the toolbar button). You get one row
per matched file and one column per Write tag, showing `old → new` for
changed tags. The header counts scanned / matched / changing tags, and
files that could not be read are reported rather than stopping the run.

If two CSV rows offer different values for the same tag on the same
file, the cell shows how many values there were; the last layer's value
is selected. Select the row and use **Choose value…** to pick a different
one. **Export preview CSV…** saves the whole preview (file, tag, old,
new, changed, source CSV + row) for review in a spreadsheet.

### 4. Apply

**Apply tab.** Choose the *Log/Backup Folder* (default `~/mp3tagging`),
then **Apply Tags**. Only files with actual changes are opened and
saved. The result panel reports per-file progress and, at the end, the
path of the change log:

```
mp3tag_20261015_103708.log.csv
Timestamp, File, Tag Name, ID3 Frame, Original/Old Value, New Value
```

Keep these logs: they are the record of what every file used to say,
and the fastest way to reverse a run by hand or with a small script.

### 5. Setup — tag names

ID3 frames have short ids (`TPE1`) and human names ("Lead Performer").
A CSV heading may use either, plus extra aliases (`Artist` = `TPE1`).
The Setup tab lists the frame → friendly-name map for the project; add,
edit, remove, or reset it. A heading that matches **nothing** becomes a
custom `TXXX` tag whose name *is* the heading — that is how fields like
`Subgenre` or `Rating` work, and files written that way can be matched by
the same heading on the next run.

Project files (**Project menu → New/Open/Save**, `.mp3p.json`) store the
file list, the CSV stack with everyone's roles, this name map, and the
log folder. They are plain JSON — you can read and even edit them.

## Command line

Everything above works headless. `mp3csvtagger --help`, and each
sub-command has its own `--help`. The project flow and the one-shot
`run` form are shown in the README; `run` is a dry run unless you pass
`--apply`.

## Tips & limits

* Matching ignores case and punctuation **only** — "The Beatles" does
  not match "Beatles". Normalise your CSV if your library is mixed.
* Embedded pictures (`APIC`) and private frames (`PRIV`) are never read
  or written as text — everything else text-shaped is fair game.
* A file with no ID3 header is fine: it starts empty, and Apply creates
  the header when it writes.
* Back up a small test folder first, check the change log, then run the
  big library. The preview is honest, but a backup is a backup.
