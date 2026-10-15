#!/usr/bin/env python3
"""Standalone entry point for the PyInstaller build (see mp3csvtagger.spec).

PyInstaller runs its entry script as a top-level module, where the
package-relative import in ``mp3csvtagger/__main__.py`` cannot work — so
the frozen build starts here instead. Running from source? Use
``mp3csvtagger`` or ``python -m mp3csvtagger``; this file is the same call.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

from mp3csvtagger.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
