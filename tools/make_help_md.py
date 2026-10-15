#!/usr/bin/env python3
"""Regenerate docs/HELP.md from the in-app help text.

The help topics live in ``src/mp3csvtagger/helptext.py`` so the GUI, this
document and other front-ends can never drift apart. Run after editing
help text:

    python tools/make_help_md.py
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from mp3csvtagger.helptext import render_markdown  # noqa: E402


def main() -> int:
    """Write docs/HELP.md next to the repository root; return exit code."""
    root = os.path.join(os.path.dirname(__file__), "..")
    out = os.path.join(root, "docs", "HELP.md")
    with open(out, "w", encoding="utf-8") as handle:
        handle.write(render_markdown())
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
