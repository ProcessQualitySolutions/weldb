#!/usr/bin/env python3
"""Pull one panel's welds out of the project weld CSVs — a fast, exact lookup.

The project's ``point_welds.csv`` / ``linear_welds.csv`` / ``area_welds.csv``
(built by ``build_weld_csvs.py`` / ``save_panel.py``) already hold every weld with
its panel, panel-prefixed ID, on-drawing bounding box and resolved properties.
This tool filters those rows by ``panel`` so you don't have to re-derive weld
counts by reading the YAML or reasoning about the drawing. Use it to answer
questions deterministically ("how many welds are on N1?") or to hand one drawing's
welds to another system (a weld-tracking database, a shipper, an ITP).

Each weld row's ``x0, y0, x1, y1`` are a **rectangle**: ``(x0, y0)`` is the
top-left corner and ``(x1, y1)`` the bottom-right corner of the weld's box on the
rendered drawing (millimetres, top-left origin, y increasing downward). They are
not two separate points.

The ``panel`` match is case-insensitive; ``--type`` narrows to one weld kind.

Usage:
    python scripts/query_welds.py N1                     # summary counts for N1
    python scripts/query_welds.py N1 --type point        # only point welds
    python scripts/query_welds.py N1 --format json       # full rows as JSON
    python scripts/query_welds.py N1 --format csv         # full rows as CSV
    python scripts/query_welds.py N1 --csv-dir ./project  # CSVs live elsewhere

This reads the CSVs only — it does not render or import the weldb library, so no
pip install and no ``fpdf2`` are needed. If the CSVs are missing or stale,
(re)build them first with ``build_weld_csvs.py`` or ``save_panel.py``.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import sys
from pathlib import Path

#: The three weld CSVs, keyed by the short type name used for ``--type``.
_CSV_BY_TYPE = {
    "point": "point_welds.csv",
    "linear": "linear_welds.csv",
    "area": "area_welds.csv",
}


def query_welds(
    csv_dir: str | Path, panel: str, types: list[str] | None = None
) -> dict[str, list[dict[str, str]]]:
    """Return one panel's weld rows from the project CSVs, grouped by weld type.

    ``types`` selects which of ``point``/``linear``/``area`` to read (default:
    all three). The ``panel`` match is case-insensitive and whitespace-stripped.
    A CSV that does not exist contributes no rows (it is simply skipped); pass an
    existing ``csv_dir`` to avoid silently matching nothing.
    """
    types = types or list(_CSV_BY_TYPE)
    target = panel.strip().casefold()
    csv_dir = Path(csv_dir)

    result: dict[str, list[dict[str, str]]] = {}
    for wtype in types:
        path = csv_dir / _CSV_BY_TYPE[wtype]
        rows: list[dict[str, str]] = []
        if path.is_file():
            reader = csv.DictReader(io.StringIO(path.read_text(encoding="utf-8")))
            rows = [r for r in reader if (r.get("panel") or "").strip().casefold() == target]
        result[wtype] = rows
    return result


def _format_summary(panel: str, welds: dict[str, list[dict[str, str]]]) -> str:
    lines = [f"Panel {panel}:"]
    total = 0
    for wtype, rows in welds.items():
        total += len(rows)
        ids = ", ".join(r.get("weld_id", "?") for r in rows)
        lines.append(f"  {wtype:<7} {len(rows):>4}" + (f"  ({ids})" if ids else ""))
    lines.append(f"  {'total':<7} {total:>4}")
    return "\n".join(lines)


def _format_csv(welds: dict[str, list[dict[str, str]]]) -> str:
    """All matched rows as one CSV, with a leading ``weld_type`` column."""
    rows: list[dict[str, str]] = []
    cols: list[str] = ["weld_type"]
    for wtype, wrows in welds.items():
        for row in wrows:
            for key in row:
                if key not in cols:
                    cols.append(key)
            rows.append({"weld_type": wtype, **row})
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=cols, restval="")
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue()


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("panel", help="Panel name to pull welds for (e.g. N1). Case-insensitive.")
    p.add_argument("--csv-dir", default=".", help="Directory holding the weld CSVs (default: cwd).")
    p.add_argument(
        "--type", choices=[*_CSV_BY_TYPE, "all"], default="all",
        help="Which weld kind to pull (default: all).",
    )
    p.add_argument(
        "--format", choices=["summary", "csv", "json"], default="summary",
        help="Output format (default: summary).",
    )
    args = p.parse_args(argv)

    csv_dir = Path(args.csv_dir)
    types = list(_CSV_BY_TYPE) if args.type == "all" else [args.type]
    present = [csv_dir / _CSV_BY_TYPE[t] for t in types]
    if not any(path.is_file() for path in present):
        looked = ", ".join(str(path) for path in present)
        raise SystemExit(
            f"No weld CSVs found ({looked}). Build them first with "
            f"build_weld_csvs.py or save_panel.py, or pass --csv-dir."
        )

    welds = query_welds(csv_dir, args.panel, types)

    if args.format == "json":
        print(json.dumps({"panel": args.panel, "welds": welds}, indent=2))
    elif args.format == "csv":
        sys.stdout.write(_format_csv(welds))
    else:
        print(_format_summary(args.panel, welds))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
