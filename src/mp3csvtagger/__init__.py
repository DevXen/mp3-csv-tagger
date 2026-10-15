"""MP3 CSV Tagger — bulk-edit MP3 ID3 tags from CSV files.

Fast, small and dependency-light: the whole engine is plain Python on
top of mutagen, and the GUI uses only the standard library.

The package is split so the *engine* never depends on the GUI:

* :mod:`mp3csvtagger.tags`      — ID3 frame names, friendly aliases, reading/writing frames
* :mod:`mp3csvtagger.mp3files`  — parallel folder/file scanning (mutagen)
* :mod:`mp3csvtagger.csvfiles`  — CSV reading
* :mod:`mp3csvtagger.matching`  — the value normalisation used for Match columns
* :mod:`mp3csvtagger.project`   — a project (MP3 paths + CSV entries + settings), JSON on disk
* :mod:`mp3csvtagger.preview`   — builds the preview: who matches, what would change
* :mod:`mp3csvtagger.apply`     — writes the chosen tags and a CSV change log
* :mod:`mp3csvtagger.cli`       — command-line interface (headless, scriptable)
* :mod:`mp3csvtagger.gui`       — Tkinter desktop app (standard library only)
"""

__version__ = "1.4.0"
__all__ = ["__version__"]
