"""Export utilities for writing weld data to JSON, CSV, and XLSX files.

These functions accept lists of PointWeld, LinearWeld, and/or AreaWeld and
serialize them to the requested format.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from weldb.models import AreaWeld, LinearWeld, PointWeld

Weld = PointWeld | LinearWeld | AreaWeld


def _point_weld_to_dict(pw: PointWeld) -> dict[str, Any]:
    return {"type": "point", "weld_id": pw.weld_id, "row": pw.row, "col": pw.col}


def _linear_weld_to_dict(lw: LinearWeld) -> dict[str, Any]:
    return {
        "type": "linear",
        "weld_id": lw.weld_id,
        "cells": [{"row": r, "col": c} for r, c in lw.cells],
    }


def _area_weld_to_dict(aw: AreaWeld) -> dict[str, Any]:
    return {
        "type": "area",
        "weld_id": aw.weld_id,
        "cells": [{"row": r, "col": c} for r, c in aw.cells],
    }


def _weld_to_dict(weld: Weld) -> dict[str, Any]:
    if isinstance(weld, PointWeld):
        return _point_weld_to_dict(weld)
    if isinstance(weld, AreaWeld):
        return _area_weld_to_dict(weld)
    return _linear_weld_to_dict(weld)


def to_json(welds: list[Weld], path: str | Path) -> None:
    """Write a list of welds to a JSON file."""
    path = Path(path)
    data = [_weld_to_dict(w) for w in welds]
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def to_csv(welds: list[Weld], path: str | Path) -> None:
    """Write a list of welds to a CSV file.

    Point welds produce one row each. Linear and area welds produce one row
    per cell.
    """
    path = Path(path)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["type", "weld_id", "row", "col"])
        for weld in welds:
            if isinstance(weld, PointWeld):
                writer.writerow(["point", weld.weld_id, weld.row, weld.col])
            else:
                kind = "area" if isinstance(weld, AreaWeld) else "linear"
                for r, c in weld.cells:
                    writer.writerow([kind, weld.weld_id, r, c])


def to_xlsx(welds: list[Weld], path: str | Path) -> None:
    """Write a list of welds to an XLSX file.

    Requires openpyxl. Raises ImportError if not installed.
    """
    try:
        from openpyxl import Workbook
    except ImportError:
        raise ImportError(
            "openpyxl is required for XLSX export. Install it with: pip install openpyxl"
        )

    path = Path(path)
    wb = Workbook()
    ws = wb.active
    ws.title = "Welds"
    ws.append(["type", "weld_id", "row", "col"])

    for weld in welds:
        if isinstance(weld, PointWeld):
            ws.append(["point", weld.weld_id, weld.row, weld.col])
        else:
            kind = "area" if isinstance(weld, AreaWeld) else "linear"
            for r, c in weld.cells:
                ws.append([kind, weld.weld_id, r, c])

    wb.save(path)
