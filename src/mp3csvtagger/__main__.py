"""Allow ``python -m mp3csvtagger`` (no arguments opens the GUI)."""

from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
