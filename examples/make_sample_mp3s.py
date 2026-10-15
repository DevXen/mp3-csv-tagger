#!/usr/bin/env python3
"""Generate a tiny sample MP3 library so you can try the program at once.

Creates ``examples/library/`` with three small (silent) MP3 files with real
ID3 tags, deliberately imperfect — wrong genre on one, a missing custom
``Rating`` field on all of them — so the example CSVs have something to fix.

Usage:  python examples/make_sample_mp3s.py
Then:   see examples/README.md for the run that tags them.
"""

from __future__ import annotations

import os
import sys

from mutagen.id3 import ID3, TALB, TCON, TIT2, TPE1

HERE = os.path.dirname(os.path.abspath(__file__))
LIBRARY = os.path.join(HERE, "library")

# One valid MPEG-1 Layer III frame header followed by zeroed frame payload,
# repeated. Enough for tag editors/players to treat the file as an MP3;
# mutagen only needs the ID3 header this script writes.
_FRAME = bytes([0xFF, 0xFB, 0x90, 0x00]) + bytes(413)
SILENT_MP3 = _FRAME * 20

TRACKS = [
    # filename, Title, Lead Performer, Album, Genre (one is wrong on purpose)
    ("01 Township Rebellion.mp3", "Township Rebellion",
     "Rage Against the Machine", "Rage Against the Machine", "Rock"),
    ("02 Killing in the Name.mp3", "Killing in the Name",
     "Rage Against the Machine", "Rage Against the Machine", "Metal"),
    ("03 Bombtrack.mp3", "Bombtrack",
     "Rage Against the Machine", "Rage Against the Machine", "Rock"),
]


def main() -> int:
    os.makedirs(LIBRARY, exist_ok=True)
    for filename, title, artist, album, genre in TRACKS:
        path = os.path.join(LIBRARY, filename)
        with open(path, "wb") as handle:
            handle.write(SILENT_MP3)
        audio = ID3()
        audio.add(TIT2(text=[title]))
        audio.add(TPE1(text=[artist]))
        audio.add(TALB(text=[album]))
        audio.add(TCON(text=[genre]))
        audio.save(path)
        print(f"wrote {path}")
    print("\nNow try (see examples/README.md):")
    print('  mp3csvtagger run --folder examples/library \\')
    print('    --csv examples/Sample1.csv --csv-roles "Lead Performer=Match,Genre=Write,Subgenre=Write" \\')
    print('    --csv examples/Sample2.csv --csv-roles "Genre=Match,Rating=Write,Comment=Write" --apply')
    return 0


if __name__ == "__main__":
    sys.exit(main())
