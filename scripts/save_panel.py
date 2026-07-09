#!/usr/bin/env python3
"""Save a .weldb panel AND render all its derived artifacts in one shot.

This is the "always render on save" entry point (see
``references/weldb_design_philosophy.md``). Instead of writing a ``.weldb`` file
and then separately running ``render_pdf.py`` and ``weld_positions.py``, this one
command validates the panel and regenerates every derived artifact together —
fewer round trips, and the PDF/JSON can never lag behind the source.

For each panel it:

  * validates the YAML by round-tripping it through the library,
  * writes (or rewrites) the ``.weldb`` file,
  * renders the drawing PDF (``<stem>.pdf``, color by default),
  * writes the weld-position map (``<stem>_weld_positions.json``),
  * optionally (``--revisions``) renders the revision-history PDF.

Two input modes:

    # Validate + render an existing/edited .weldb file already on disk:
    python scripts/save_panel.py N5.weldb
    python scripts/save_panel.py N5.weldb --canvas-w 1000 --canvas-h 800
    python scripts/save_panel.py N5.weldb --no-color --revisions

    # One-shot create: pipe the YAML in on stdin and it is written + rendered:
    python scripts/save_panel.py N5.weldb --stdin < draft.yaml

Requires fpdf2 (``pip install fpdf2``) to render. If it is missing, the ``.weldb``
file is still written (source of truth first) and the PDF/JSON steps are skipped
with a warning — pass ``--no-render`` to skip them deliberately.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from weldb import loads, save_panel  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("file", help="Path to the .weldb file to write/validate and render.")
    p.add_argument("--stdin", action="store_true",
                   help="Read the YAML content from stdin and write it to <file> before rendering.")
    p.add_argument("--no-color", dest="color", action="store_false", help="Render the PDF black-on-white.")
    p.add_argument("--revisions", action="store_true", help="Also render the revision-history PDF.")
    p.add_argument("--no-render", dest="render", action="store_false",
                   help="Only write/validate the .weldb; skip the PDF and weld-position JSON.")
    p.add_argument("--canvas-w", type=float, help="Target canvas width in pixels (enables px output in the JSON).")
    p.add_argument("--canvas-h", type=float, help="Target canvas height in pixels (enables px output in the JSON).")
    p.set_defaults(color=True, render=True)
    args = p.parse_args(argv)

    if (args.canvas_w is None) != (args.canvas_h is None):
        raise SystemExit("Provide both --canvas-w and --canvas-h for pixel output, or neither.")
    if args.canvas_w is not None and (args.canvas_w <= 0 or args.canvas_h <= 0):
        raise SystemExit("--canvas-w and --canvas-h must be positive.")

    path = Path(args.file)
    if args.stdin:
        content = sys.stdin.read()
    else:
        if not path.is_file():
            raise SystemExit(f"File not found: {path} (use --stdin to create it from piped YAML).")
        content = path.read_text(encoding="utf-8")

    # Round-trip through the library: this validates required fields and grids,
    # and is what gets (re)written to disk in canonical form.
    doc = loads(content)

    try:
        written = save_panel(
            doc, path, color=args.color, canvas_w=args.canvas_w, canvas_h=args.canvas_h,
            revisions=args.revisions, render=args.render,
        )
    except ImportError as exc:
        # The .weldb itself was already written by save_panel before rendering,
        # so the source of truth is safe; only the PDF/JSON were skipped.
        print(
            f"Wrote {path} (validated). PDF/weld-position rendering skipped — needs fpdf2: {exc}\n"
            "Install it (`pip install fpdf2`) or build an HTML artifact instead "
            "(references/html_artifact_editor.md).",
            file=sys.stderr,
        )
        return 1

    labels = {
        "weldb": "panel", "pdf": "PDF", "weld_positions": "weld positions",
        "revisions_pdf": "revision history",
    }
    print("Saved and rendered:" if len(written) > 1 else "Saved (not rendered):")
    for role, out in written.items():
        print(f"  {labels.get(role, role):16} {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
