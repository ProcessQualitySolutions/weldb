#!/usr/bin/env python3
"""Render a panel's full, unabridged revision history to a standalone PDF.

Lists every revision in the ``maps`` array (Rev, Date, Updated By, Comments),
oldest to newest, paginated as needed. By default writes
``<stem>_revisions.pdf`` beside the source; pass ``-o`` to choose a path.

Usage:
    python scripts/render_revision_history.py N5.weldb   # -> N5_revisions.pdf

Requires fpdf2 (``pip install fpdf2``).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from weldb import render_revision_history_pdf  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("file", help="Path to the .weldb file.")
    p.add_argument("-o", "--output", help="Output PDF path (default: <stem>_revisions.pdf beside the source).")
    args = p.parse_args(argv)

    src = Path(args.file)
    if not src.is_file():
        raise SystemExit(f"File not found: {src}")

    try:
        out = render_revision_history_pdf(src, output_path=args.output)
    except ImportError as exc:
        raise SystemExit(f"PDF rendering needs fpdf2: {exc}\nInstall it with `pip install fpdf2`.")
    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
