# Examples

A three-file sample library plus two layered CSVs (`Sample1.csv` and
`Sample2.csv`) that demonstrate the layering pattern.

```bash
python examples/make_sample_mp3s.py

mp3csvtagger run \
  --folder examples/library \
  --csv examples/Sample1.csv \
  --csv-roles "Lead Performer=Match,Genre=Write,Subgenre=Write" \
  --csv examples/Sample2.csv \
  --csv-roles "Genre=Match,Rating=Write,Comment=Write"
```

That command is a dry run — add `--apply` to write the tags.

What happens:

* **Sample1** matches every track by Lead Performer
  ("Rage Against the Machine") and writes Genre = *Rap Metal* plus a
  custom `Subgenre` field (a TXXX tag, because there is no standard
  Subgenre frame).
* **Sample2** is a *layer*: it matches on Genre = *Rap Metal*, a value
  that only exists because Sample1 writes it, and adds `Rating` = 5
  (another custom tag) and a Comment.

In the GUI, roles are set per column on the CSV tab instead — same
engine, same result.
