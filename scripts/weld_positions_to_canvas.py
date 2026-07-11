#!/usr/bin/env python3
"""Convert a panel's PDF weld positions into HTML5-canvas pixel positions.

Give it a panel name plus the target canvas's width and height (in pixels) and it
returns every weld's box in **canvas pixel coordinates**, ready to POST to a
canvas-based weld tracking system. It does the whole conversion programmatically —
no inference, no round trips to reason about geometry.

How the conversion works (all derived from the source, not guessed):

  * The weld boxes are measured on the panel's own rendered PDF page — reproduced
    from the exact same layout math weldb draws with (letter, landscape;
    ~279.4 x 215.9 mm), located from the panel name. Coordinates are millimetres
    with the origin at the **top-left**, x growing right and y growing **down**.
  * An HTML5 canvas uses that *same* orientation (top-left origin, y down), so the
    map is a single positive uniform scale — **no vertical flip, no translation**:
        scale = canvas_width / page_width_mm   (pixels per millimetre)
        x_px = x_mm * scale ;  y_px = y_mm * scale
  * Scaling is keyed to the canvas **width** (the drawing fills the canvas
    horizontally). The canvas **height** is used to *validate* that no weld lands
    outside the canvas: every corner must satisfy 0 <= x <= width and
    0 <= y <= height. If any weld would fall outside, the tool reports which ones
    and the minimum height needed, and exits non-zero (pass
    ``--allow-out-of-bounds`` to emit the payload anyway, with per-weld
    ``in_bounds`` flags). A canvas whose aspect ratio matches the drawing's always
    fits.

Each weld is reported once (its leftmost-view box) under its panel-prefixed
project ID (``N1.T100``). Get the ``--width``/``--height`` from the weld tracking
program's uploaded drawing canvas.

One such tracker is **qcdatabase.ai** (https://qcdatabase.ai), which pins each weld
as a "map item" on an uploaded drawing using this exact canvas system (top-left
origin, y down). When its ``qcdatabase`` MCP server is installed, upload the panel
PDF, read the sheet's pixel ``width``/``height`` with ``get_drawing``, run this tool
with those dimensions, then POST the JSON via ``bulk_create_map_items`` (project
weld ID -> ``label``). **Every weldb weld is a rectangle**, so the Weld schema's
``is_rect`` map-item setting MUST be on: map ``x0,y0`` -> ``x_position,y_position``
and ``x1,y1`` -> ``x_position_2,y_position_2`` (top-left and lower-right corners).
Each weld in the output carries the box corners (``x0,y0,x1,y1``) only. If
``is_rect`` is off on the schema, do NOT collapse the box to a point — stop and tell
the user to enable rectangular welds first. See SKILL.md, "Pushing welds to a
canvas-based weld tracking system," for the full flow.

Usage:
    python scripts/weld_positions_to_canvas.py N1 --width 1200 --height 900
    python scripts/weld_positions_to_canvas.py N1 --width 1200 --height 900 --format summary
    python scripts/weld_positions_to_canvas.py N1 --width 1200 --height 700 --allow-out-of-bounds
    python scripts/weld_positions_to_canvas.py ./project/N1.weldb --width 1200 --height 900

The weldb library is bundled; no pip install is required. Measuring the page needs
``fpdf2`` (``pip install fpdf2``).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from weldb import load, weld_canvas_boxes  # noqa: E402


def _resolve_panel_file(panel: str, directory: str) -> Path:
    """Find the .weldb for a panel — a direct path, or ``<panel>.weldb`` in dir."""
    p = Path(panel)
    if p.suffix == ".weldb":
        if not p.is_file():
            raise SystemExit(f"No such file: {p}")
        return p
    candidate = Path(directory) / f"{panel}.weldb"
    if not candidate.is_file():
        raise SystemExit(
            f"No .weldb found for panel '{panel}' (looked for {candidate}). "
            f"Pass --dir or a path to the file."
        )
    return candidate


def _format_summary(result: dict) -> str:
    lines = [
        f"Panel {result['panel_name']} -> canvas "
        f"{result['canvas_width']}x{result['canvas_height']} px",
        f"  page {result['page_width']}x{result['page_height']} mm, "
        f"scale {result['scale']} px/mm, origin {result['origin']} (y down, no flip)",
        f"  {len(result['welds'])} weld(s); "
        f"min canvas height to fit = {result['required_canvas_height']} px",
    ]
    oob = result["out_of_bounds"]
    if oob:
        lines.append(f"  OUT OF BOUNDS ({len(oob)}): {', '.join(oob)}")
    else:
        lines.append("  all welds within canvas bounds")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("panel", help="Panel name (e.g. N1) or a path to its .weldb file.")
    p.add_argument("--width", type=float, required=True, help="Target canvas width in pixels (drives the scale).")
    p.add_argument("--height", type=float, required=True, help="Target canvas height in pixels (bounds check).")
    p.add_argument("--dir", default=".", help="Directory to find <panel>.weldb in (default: cwd).")
    p.add_argument("--format", choices=["json", "summary"], default="json", help="Output format (default: json).")
    p.add_argument(
        "--allow-out-of-bounds", action="store_true",
        help="Emit the payload even if some welds fall outside the canvas (default: fail instead).",
    )
    args = p.parse_args(argv)

    path = _resolve_panel_file(args.panel, args.dir)
    try:
        result = weld_canvas_boxes(load(path), args.width, args.height)
    except ImportError as exc:
        raise SystemExit(str(exc))
    except ValueError as exc:
        raise SystemExit(str(exc))

    oob = result["out_of_bounds"]
    if oob and not args.allow_out_of_bounds:
        print(
            f"{len(oob)} weld(s) fall outside the {args.width:g}x{args.height:g} canvas: "
            f"{', '.join(oob)}.\n"
            f"Scaling by width needs a canvas at least "
            f"{result['required_canvas_height']:g} px tall (you gave {args.height:g}). "
            f"Fix the canvas height, or pass --allow-out-of-bounds to emit anyway.",
            file=sys.stderr,
        )
        return 1

    if args.format == "summary":
        print(_format_summary(result))
    else:
        print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
