#!/usr/bin/env python3
"""Build point/linear/area weld CSVs from a set of .weldb files.

Give it one or more .weldb files or a directory; it writes
``point_welds.csv``, ``linear_welds.csv`` and
``area_welds.csv``. Each weld row carries its effective properties — the panel's
top-level properties merged with type-level and weld-specific overrides. Point
welds are deduplicated across a project (a duplicate prefixed ID is an error);
any file that fails to load or validate is reported and skipped, never partially
included.

Usage:
    python scripts/build_weld_csvs.py ./project           # a directory of .weldb
    python scripts/build_weld_csvs.py N5.weldb N6.weldb    # explicit files
    python scripts/build_weld_csvs.py ./project --out-dir ./project

The weldb library is bundled; no pip install is required.
"""

from __future__ import annotations

import argparse
import csv
import io
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from weldb import (  # noqa: E402
    get_area_welds,
    get_linear_welds,
    get_point_welds,
    loads,
    prefix_weld_id,
    resolve_weld_properties,
)

_PROP_EXCLUDE = {"panel_name"}


def _weld_props(props_by_id: dict[str, dict[str, Any]], cell: str) -> dict[str, Any]:
    props = props_by_id.get(cell, {})
    return {k: v for k, v in props.items() if k not in _PROP_EXCLUDE}


def _weld_csv_text(rows: list[dict[str, Any]], id_cols: list[str]) -> str:
    prop_cols: list[str] = []
    for row in rows:
        for key in row:
            if key not in id_cols and key not in prop_cols:
                prop_cols.append(key)
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=id_cols + prop_cols, restval="")
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue()


def _collect_files(inputs: list[str]) -> list[Path]:
    files: list[Path] = []
    for item in inputs:
        p = Path(item)
        if p.is_dir():
            files.extend(sorted(p.glob("*.weldb")))
        elif p.is_file():
            files.append(p)
        else:
            raise SystemExit(f"Not a file or directory: {p}")
    if not files:
        raise SystemExit("No .weldb files found in the given input(s).")
    return files


def build_csvs(files: list[Path]) -> tuple[dict[str, str], dict[str, int], list[str]]:
    point_rows: list[dict[str, Any]] = []
    linear_rows: list[dict[str, Any]] = []
    area_rows: list[dict[str, Any]] = []
    seen_points: dict[str, str] = {}
    skipped: list[str] = []

    for path in files:
        label = path.name
        try:
            doc = loads(path.read_text(encoding="utf-8"))
            panel_name = doc["panel_name"]
            source = path.name
            props_by_id = resolve_weld_properties(doc)

            point_welds = get_point_welds(doc)
            linear_welds = get_linear_welds(doc)
            area_welds = get_area_welds(doc)

            # Cross-file point-weld dedup, checked before committing any rows so a
            # rejected file leaves the accumulators clean.
            file_point_ids: dict[str, str] = {}
            for pw in point_welds:
                prefixed_id = prefix_weld_id(panel_name, pw.weld_id)
                if prefixed_id in seen_points:
                    raise ValueError(
                        f"Duplicate weld '{prefixed_id}' also in {seen_points[prefixed_id]}"
                    )
                file_point_ids[pw.weld_id] = prefixed_id

            new_point = [
                {"panel": panel_name, "weld_id": file_point_ids[pw.weld_id], "source": source,
                 **_weld_props(props_by_id, pw.weld_id)}
                for pw in point_welds
            ]
            new_linear = [
                {"panel": panel_name, "weld_id": prefix_weld_id(panel_name, lw.weld_id), "source": source,
                 **_weld_props(props_by_id, lw.weld_id)}
                for lw in linear_welds
            ]
            new_area = [
                {"panel": panel_name, "weld_id": prefix_weld_id(panel_name, aw.weld_id), "source": source,
                 **_weld_props(props_by_id, aw.weld_id)}
                for aw in area_welds
            ]

            for prefixed_id in file_point_ids.values():
                seen_points[prefixed_id] = source
            point_rows.extend(new_point)
            linear_rows.extend(new_linear)
            area_rows.extend(new_area)
        except Exception as exc:  # noqa: BLE001 — report and skip, never abort
            skipped.append(f"{label}: {exc}")

    id_cols = ["panel", "weld_id", "source"]
    texts = {
        "point_welds.csv": _weld_csv_text(point_rows, id_cols),
        "linear_welds.csv": _weld_csv_text(linear_rows, id_cols),
        "area_welds.csv": _weld_csv_text(area_rows, id_cols),
    }
    counts = {"point": len(point_rows), "linear": len(linear_rows), "area": len(area_rows)}
    return texts, counts, skipped


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("inputs", nargs="+", help="One or more .weldb files, and/or directories of them.")
    p.add_argument("--out-dir", default=".", help="Directory to write the three CSVs into (default: cwd).")
    args = p.parse_args(argv)

    files = _collect_files(args.inputs)
    texts, counts, skipped = build_csvs(files)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, text in texts.items():
        (out_dir / name).write_text(text, encoding="utf-8")

    print(
        f"Wrote {', '.join(texts)} to {out_dir} — "
        f"{counts['point']} point, {counts['linear']} linear, {counts['area']} area rows."
    )
    if skipped:
        print("Skipped (fix and re-run):")
        for s in skipped:
            print(f"  - {s}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
