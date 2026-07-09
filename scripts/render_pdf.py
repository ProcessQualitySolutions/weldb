#!/usr/bin/env python3
"""Render a .weldb panel to a single-sheet engineering-drawing PDF.

Runs locally against the bundled library. Renders **in color by default** (pass
``--no-color`` for black-on-white). By default the PDF is written next to the
source (``N5.weldb`` -> ``N5.pdf``); pass ``-o`` to choose a path.

Usage:
    python scripts/render_pdf.py N5.weldb            # -> N5.pdf (color)
    python scripts/render_pdf.py N5.weldb --no-color -o out/N5.pdf

Requires fpdf2 (``pip install fpdf2``). If the sandbox can't render PDFs, build
an interactive HTML artifact instead — see references/html_artifact_editor.md.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from weldb import render_pdf  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("file", help="Path to the .weldb file to render.")
    p.add_argument("-o", "--output", help="Output PDF path (default: <stem>.pdf beside the source).")
    p.add_argument("--color", dest="color", action="store_true",
                   help="Tint grid cells and legend swatches by weld type (default).")
    p.add_argument("--no-color", dest="color", action="store_false", help="Render black-on-white.")
    p.set_defaults(color=True)
    args = p.parse_args(argv)

    src = Path(args.file)
    if not src.is_file():
        raise SystemExit(f"File not found: {src}")

    try:
        out = render_pdf(src, color=args.color, output_path=args.output)
    except ImportError as exc:
        raise SystemExit(
            f"PDF rendering needs fpdf2: {exc}\n"
            "Install it (`pip install fpdf2`) or build an HTML artifact instead "
            "(references/html_artifact_editor.md)."
        )
    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
