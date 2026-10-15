# CSV Format

* **Encoding:** UTF-8 (a UTF-8 BOM, as Excel writes, is accepted).
* **Dialect:** standard comma-separated, `"` quoting — anything Excel,
  LibreOffice or Google Sheets exports works.
* **Header row:** required. Each cell is a *tag name*.
* **Data rows:** one candidate set of tag values per row. Blank rows are
  skipped; short rows are padded with empty values rather than rejected.

## Tag names (column headings)

A heading resolves to an ID3 frame in this order:

1. **A frame id** — `TIT2`, `TPE1`, `TCON`, … (four characters,
   case-insensitive).
2. **A friendly name** from the project's map — `Title`→TIT2,
   `Lead Performer`→TPE1, `Band`→TPE2, `Album`→TALB, `Genre`→TCON,
   `Year`→TYER, … plus the aliases `Artist`→TPE1, `Track`→TRCK,
   `Date`→TDRC (see the Setup tab for the full, editable list).
3. **Anything else** becomes a **custom `TXXX` tag** named after the
   heading: `Subgenre`, `Rating`, `Mood`… Writing is only half of it —
   the same heading reads the value back, so a second run can Match on a
   custom field an earlier run wrote.

## Roles

Every column of every CSV has exactly one role per CSV file:

* **Match (1)** — participates in deciding which files a row applies to.
* **Write (2)** — the row's value is written to matched files.
* **Skip (3)** — ignored.

(The numbers are the original program's and appear in project files.)

## Matching rule

For a row to apply to a file, **all** of its Match columns must equal the
file's current values after normalisation: trim, lower-case, delete all
ASCII punctuation. So:

| File value | CSV value | Match? |
|---|---|---|
| Don't Stop! | dont stop | ✅ |
| Rage Against the Machine | rage against the machine | ✅ |
| The Beatles | Beatles | ❌ (different words) |
| AC/DC | ACDC | ✅ (punctuation deleted) |

A CSV with **no Match columns** applies every row to every scanned file.
A CSV with no Write columns changes nothing.

## Layers

CSVs apply in the order they are listed. After a layer runs, its
selected writes become the files' effective values for the next layer —
the standard trick is one CSV that normalises a field and a second that
keys off the normalised value (see `examples/`). When several rows (in
one or several layers) write the same tag on the same file, all values
are kept as candidates in the preview, the **last layer's value is
selected by default**, and you can select another in the GUI.

## Example

`artists.csv`:

```csv
Lead Performer,Genre
Rage Against the Machine,Rap Metal
```

with `Lead Performer=Match, Genre=Write` sets the genre of every track
whose lead performer matches — regardless of which album or title each
track has.
