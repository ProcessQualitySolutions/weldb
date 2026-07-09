#!/usr/bin/env python3
"""Locate every weld on a panel's rendered PDF, as a JSON coordinate map.

For each weld region it reports a bounding box (upper-left ``x0,y0`` / lower-right ``x1,y1``) in the rendered
PDF's coordinate space: millimetres, origin top-left, y increasing downward
(matches screen/canvas space — no vertical flip). Page width/height (mm) are
included so a consumer can map the boxes onto any canvas.

Pass ``--canvas-w`` and ``--canvas-h`` (target pixels) to also get integer pixel
corners ``px0,py0,px1,py1`` scaled proportionally — e.g. to drop pins/hotspots
onto a QC Database image. By default writes ``<stem>_weld_positions.json`` beside
the source; pass ``-o`` for another path, or ``--stdout`` to print.

Usage:
    python scripts/weld_positions.py N5.weldb
    python scripts/weld_positions.py N5.weldb --canvas-w 1000 --canvas-h 800

Requires fpdf2 (``pip install fpdf2``) — geometry is derived from the same layout
math the PDF renderer uses.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from weldb import loads, weld_positions_data  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("file", help="Path to the .weldb file.")
    p.add_argument("-o", "--output", help="Output JSON path (default: <stem>_weld_positions.json).")
    p.add_argument("--stdout", action="store_true", help="Print JSON to stdout instead of writing a file.")
    p.add_argument("--canvas-w", type=float, help="Target canvas width in pixels (enables px output).")
    p.add_argument("--canvas-h", type=float, help="Target canvas height in pixels (enables px output).")
    p.add_argument("--include-text", action="store_true",
                   help="Also report plain-text regions (tube numbers, annotations), not just welds.")
    args = p.parse_args(argv)

    if (args.canvas_w is None) != (args.canvas_h is None):
        raise SystemExit("Provide both --canvas-w and --canvas-h for pixel output, or neither.")
    if args.canvas_w is not None and (args.canvas_w <= 0 or args.canvas_h <= 0):
        raise SystemExit("--canvas-w and --canvas-h must be positive.")

    src = Path(args.file)
    if not src.is_file():
        raise SystemExit(f"File not found: {src}")

    doc = loads(src.read_text(encoding="utf-8"))
    try:
        data = weld_positions_data(
            doc, include_text=args.include_text, canvas_w=args.canvas_w, canvas_h=args.canvas_h
        )
    except ImportError as exc:
        raise SystemExit(f"Weld-position extraction needs fpdf2: {exc}\nInstall it with `pip install fpdf2`.")

    text = json.dumps(data, indent=2)
    if args.stdout:
        sys.stdout.write(text + "\n")
        return 0

    panel_name = data.get("panel_name") or doc.get("panel_name", "panel")
    out = Path(args.output) if args.output else src.with_name(f"{panel_name}_weld_positions.json")
    out.write_text(text, encoding="utf-8")
    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
