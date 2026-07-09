#!/usr/bin/env python3
"""Generate a conventional water-wall panel scaffold — EXTENDED membrane style.

Same task as ``create_panel.py``, but the membrane welds are drawn extending PAST
the tube point welds (a numbers-only header/footer row, and a membrane row above
and below each weld row), so the membranes read as continuous full-length bars.
See ``examples/conventional_panel_extended_membrane_style/``.

**This is the default style — prefer it unless the user asks for the simplified
style.** The scaffold has a single ``hot_side`` view (normal panels are hot-side
only; add ``--cold-side`` or ``--view NAME`` for more). Tubes are numbered
left-to-right as seen from the hot side: ``--tube-start`` is the leftmost tube.
This is a STARTING SCAFFOLD — edit the YAML afterwards (ports, clips, area welds,
dutchmen, weld-length overrides, dropped/offset tubes, extra views, custom fields)
to match the real request. See ``references/drawing_spec.md`` and ``examples/``.

Usage:
    python scripts/create_panel_extended_membrane.py N5 --mtrl "SA-210 A1" \\
        --od 2.0 --wall 0.15 --units in --elevation "1850 in" \\
        --tube-start 250 --tube-end 254

The weldb library is bundled with this skill; no pip install is required.
"""

from __future__ import annotations

import argparse

from _panel_common import add_common_args, build_doc, build_extended_grid, write_result


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    add_common_args(p)
    args = p.parse_args(argv)
    doc = build_doc(args, build_extended_grid)
    return write_result(args, doc, "extended membrane style")


if __name__ == "__main__":
    raise SystemExit(main())
