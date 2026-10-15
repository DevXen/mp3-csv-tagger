# Building

## Development

```bash
git clone https://github.com/DevXen/mp3-csv-tagger
cd mp3-csv-tagger
python -m venv .venv
.venv\Scripts\activate          # Windows;  source .venv/bin/activate on Linux/macOS
pip install -e .
python -m pytest                # the engine test-suite
mp3csvtagger                    # GUI
mp3csvtagger run --help         # CLI
```

The engine (`preview.py`, `apply.py`, `project.py`, `mp3files.py`,
`csvfiles.py`, `tags.py`, `matching.py`) has no GUI imports — the GUI and
the CLI are both thin front-ends over it, and the tests exercise the
engine directly.

## Windows standalone (.exe)

The standalone distribution is one PyInstaller build:

```bat
build_windows.bat
```

which installs the project + PyInstaller into a build venv and runs
`mp3csvtagger.spec`, producing `dist\MP3CsvTagger\MP3CsvTagger.exe`
(64-bit, current Python) with its support files in the same folder — zip
that folder and that is the download. The spec is a *onedir* build:
startup is fast because nothing has to unpack itself on every launch
(one of the small taxes the old single-file build charged).

## Versioning

The version lives in `pyproject.toml` and `src/mp3csvtagger/__init__.py` —
keep them in step (the test-suite does not check this; humans do).
