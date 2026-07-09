#!/usr/bin/env python3
"""Save a .weldb panel AND regenerate all its derived artifacts in one shot.

This is the "always render on save" entry point (see
``references/weldb_design_philosophy.md``). Instead of writing a ``.weldb`` file
and then separately rendering it and rebuilding the weld CSVs, this one command
validates the panel and regenerates every derived artifact together — fewer round
trips, and the PDF/CSVs can never lag behind the source.

For the panel it:

  * validates the YAML by round-tripping it through the library,
  * writes (or rewrites) the ``.weldb`` file,
  * renders the drawing PDF (``<stem>.pdf``, color by default),
  * optionally (``--revisions``) renders the revision-history PDF,

and then rebuilds the project-wide weld CSVs (``point_welds.csv``,
``linear_welds.csv``, ``area_welds.csv``) for the panel's directory, so every
weld's on-drawing coordinates (``x0, y0, x1, y1``, leftmost view) stay current.

Rendering is **not optional** — a panel is never saved without its PDF and the
refreshed CSVs.

Two input modes:

    # Validate + render an existing/edited .weldb file already on disk:
    python scripts/save_panel.py N5.weldb
    python scripts/save_panel.py N5.weldb --no-color --revisions

    # One-shot create: pipe the YAML in on stdin and it is written + rendered:
    python scripts/save_panel.py N5.weldb --stdin < draft.yaml

Requires fpdf2 (``pip install fpdf2``) to render. If it is missing, the ``.weldb``
file is still written (source of truth first) but the command fails so the stale
state is obvious — install fpdf2 or build an HTML artifact instead
(``references/html_artifact_editor.md``).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from build_weld_csvs import build_csvs  # noqa: E402  (sibling script)

from weldb import loads, save_panel  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("file", help="Path to the .weldb file to write/validate and render.")
    p.add_argument("--stdin", action="store_true",
                   help="Read the YAML content from stdin and write it to <file> before rendering.")
    p.add_argument("--no-color", dest="color", action="store_false", help="Render the PDF black-on-white.")
    p.add_argument("--revisions", action="store_true", help="Also render the revision-history PDF.")
    p.set_defaults(color=True)
    args = p.parse_args(argv)

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
        written = save_panel(doc, path, color=args.color, revisions=args.revisions)
    except ImportError as exc:
        # The .weldb itself was already written by save_panel before rendering,
        # so the source of truth is safe; only the PDF was skipped.
        raise SystemExit(
            f"Wrote {path} (validated) but could not render — needs fpdf2: {exc}\n"
            "Install it (`pip install fpdf2`) or build an HTML artifact instead "
            "(references/html_artifact_editor.md)."
        )

    # Rebuild the project-wide weld CSVs for the panel's directory so the saved
    # panel's welds and their coordinates are reflected immediately.
    out_dir = path.parent if str(path.parent) else Path(".")
    files = sorted(out_dir.glob("*.weldb"))
    texts, counts, skipped = build_csvs(files)
    for name, text in texts.items():
        (out_dir / name).write_text(text, encoding="utf-8")

    labels = {"weldb": "panel", "pdf": "PDF", "revisions_pdf": "revision history"}
    print("Saved and rendered:")
    for role, out in written.items():
        print(f"  {labels.get(role, role):16} {out}")
    print(
        f"  {'CSVs':16} {out_dir} — "
        f"{counts['point']} point, {counts['linear']} linear, {counts['area']} area rows."
    )
    if skipped:
        print("CSV skipped (fix and re-run):", file=sys.stderr)
        for s in skipped:
            print(f"  - {s}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
