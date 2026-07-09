#!/usr/bin/env python3
"""Create AND render MANY panels from one spec, in a single process.

Instead of invoking ``create_panel*`` once per panel (each paying Python + fpdf2
startup, and each a separate round trip), this scaffolds a whole set of panels
from one JSON spec and renders every panel's PDF + weld-position JSON on save.
Fewer round trips, one interpreter start.

Ideal for panels that belong together — **stacked** (two panels on the same tubes,
one above the other), **adjacent** (side by side on the same wall), or
**overlapping** panels — because those are defined as a set and share a boundary.

    ⚠ Shared tube / membrane welds: whenever you lay out stacked, adjacent, or
    overlapping panels, understand which tube and membrane welds are *shared*
    across the boundary. A weld at the seam between two panels is ONE physical
    weld and must be recorded on ONE panel only — weld IDs are unique across the
    whole project (see references/project_spec.md and the adjacent_panels /
    stacked_panels / overlapping_panels examples). Do not duplicate a shared
    boundary weld onto both panels.

Spec format — a JSON array of panel objects. Each object mirrors the
``create_panel*`` options (underscored keys). Required per panel: ``panel_name``,
``mtrl``, ``od``, ``wall``, ``units``, ``elevation``, ``tube_start``,
``tube_end``. Optional: ``style`` (``"extended"`` default, or ``"simplified"``),
``body_rows``, ``cold_side`` (bool), ``views`` (list of extra view names),
``fields`` (object of custom top-level fields), ``elevation_at``, ``updated_by``,
``comments``.

    [
      {"panel_name": "N5", "mtrl": "SA-210 A1", "od": 2.0, "wall": 0.15,
       "units": "in", "elevation": "1850 in", "tube_start": 250, "tube_end": 254},
      {"panel_name": "N6", "mtrl": "SA-210 A1", "od": 2.0, "wall": 0.15,
       "units": "in", "elevation": "1850 in", "tube_start": 255, "tube_end": 259}
    ]

Usage:
    python scripts/create_panels.py --spec panels.json --out-dir ./project
    python scripts/create_panels.py --out-dir ./project < panels.json

The whole spec is validated before anything is written, so a bad panel aborts the
batch without leaving a half-created set. Rendering needs fpdf2 (``pip install
fpdf2``); without it the ``.weldb`` files are still written and the PDFs/JSON are
skipped with a warning. Every panel is a STARTING SCAFFOLD — edit each YAML to the
real panel, then re-save with ``scripts/save_panel.py``.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from _panel_common import (  # noqa: E402
    DEFAULT_BODY_ROWS,
    build_doc,
    build_extended_grid,
    build_simplified_grid,
)

from weldb import save_panel  # noqa: E402

# Per-panel spec keys and their defaults (keys with no default are required).
_DEFAULTS = {
    "style": "extended",
    "body_rows": DEFAULT_BODY_ROWS,
    "cold_side": False,
    "views": None,
    "fields": None,
    "elevation_at": "",
    "updated_by": "skill",
    "comments": "Initial weld map layout",
}
_REQUIRED = ("panel_name", "mtrl", "od", "wall", "units", "elevation", "tube_start", "tube_end")
_GRID_BUILDERS = {"extended": build_extended_grid, "simplified": build_simplified_grid}


def _namespace_for(panel: dict, index: int) -> argparse.Namespace:
    """Turn one spec object into the argparse.Namespace ``build_doc`` expects."""
    if not isinstance(panel, dict):
        raise SystemExit(f"Panel #{index + 1}: expected an object, got {type(panel).__name__}.")
    missing = [k for k in _REQUIRED if k not in panel]
    if missing:
        name = panel.get("panel_name", f"#{index + 1}") if isinstance(panel, dict) else f"#{index + 1}"
        raise SystemExit(f"Panel {name}: missing required field(s): {', '.join(missing)}.")
    unknown = set(panel) - set(_REQUIRED) - set(_DEFAULTS)
    if unknown:
        raise SystemExit(f"Panel {panel['panel_name']}: unknown field(s): {', '.join(sorted(unknown))}.")

    merged = {**_DEFAULTS, **panel}
    if merged["style"] not in _GRID_BUILDERS:
        raise SystemExit(
            f"Panel {panel['panel_name']}: unknown style '{merged['style']}' "
            f"(use {' or '.join(_GRID_BUILDERS)})."
        )
    fields = merged["fields"] or {}
    if not isinstance(fields, dict):
        raise SystemExit(f"Panel {panel['panel_name']}: 'fields' must be an object.")

    # build_doc reads argparse-style attributes: `field` (list of k=v) and `view`.
    return argparse.Namespace(
        panel_name=merged["panel_name"],
        mtrl=merged["mtrl"], od=merged["od"], wall=merged["wall"],
        units=merged["units"], elevation=merged["elevation"],
        tube_start=merged["tube_start"], tube_end=merged["tube_end"],
        elevation_at=merged["elevation_at"], updated_by=merged["updated_by"],
        comments=merged["comments"], body_rows=merged["body_rows"],
        cold_side=bool(merged["cold_side"]), view=merged["views"],
        field=[f"{k}={v}" for k, v in fields.items()],
    )


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--spec", help="Path to the JSON spec (default: read from stdin).")
    p.add_argument("--out-dir", default=".", help="Directory to write each <panel>.weldb into (default: cwd).")
    p.add_argument("--no-color", dest="color", action="store_false", help="Render PDFs black-on-white.")
    p.add_argument("--no-render", dest="render", action="store_false",
                   help="Only write the .weldb scaffolds; skip rendering PDFs and weld-position JSON.")
    p.set_defaults(color=True, render=True)
    args = p.parse_args(argv)

    raw = Path(args.spec).read_text(encoding="utf-8") if args.spec else sys.stdin.read()
    try:
        spec = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid JSON spec: {exc}")
    if not isinstance(spec, list) or not spec:
        raise SystemExit("Spec must be a non-empty JSON array of panel objects.")

    # Validate + build EVERY panel first, so a bad entry aborts before any writes.
    built: list[tuple[str, dict]] = []
    for i, panel in enumerate(spec):
        ns = _namespace_for(panel, i)
        doc = build_doc(ns, _GRID_BUILDERS[(panel.get("style") or "extended")])
        built.append((ns.panel_name, doc))

    names = [n for n, _ in built]
    if len(set(names)) != len(names):
        dupes = sorted({n for n in names if names.count(n) > 1})
        raise SystemExit(f"Duplicate panel_name(s) in spec: {', '.join(dupes)}.")

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"Created {len(built)} panel(s) in {out_dir}:")
    render_warned = False
    for name, doc in built:
        out = out_dir / f"{name}.weldb"
        try:
            written = save_panel(doc, out, color=args.color, render=args.render)
        except ImportError:
            written = {"weldb": out}  # YAML written; rendering skipped
            render_warned = True
        pdf = written.get("pdf")
        print(f"  {name:10} {out}" + (f"   -> {pdf}" if pdf else ""))

    if render_warned:
        print(
            "WARNING: fpdf2 not installed — PDFs and weld positions were skipped. "
            "Install it with `pip install fpdf2`.",
            file=sys.stderr,
        )
    print(
        "\nEach panel is a scaffold — edit its YAML to the real layout, minding "
        "SHARED tube/membrane welds across stacked/adjacent/overlapping panels "
        "(record each boundary weld on ONE panel only), then re-save with "
        "scripts/save_panel.py."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
