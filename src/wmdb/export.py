"""Shared export utilities for writing weld data to JSON, CSV, and XLSX files.

These functions accept lists of PointWeld and/or LinearWeld from any standard
(boiler, pipeline, iron) and serialize them to the requested format.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from wmdb.types import LinearWeld, PointWeld


def _point_weld_to_dict(pw: PointWeld) -> dict[str, Any]:
    return {"type": "point", "weld_id": pw.weld_id, "row": pw.row, "col": pw.col}


def _linear_weld_to_dict(lw: LinearWeld) -> dict[str, Any]:
    return {
        "type": "linear",
        "weld_id": lw.weld_id,
        "cells": [{"row": r, "col": c} for r, c in lw.cells],
    }


def _weld_to_dict(weld: PointWeld | LinearWeld) -> dict[str, Any]:
    if isinstance(weld, PointWeld):
        return _point_weld_to_dict(weld)
    return _linear_weld_to_dict(weld)


def to_json(welds: list[PointWeld | LinearWeld], path: str | Path) -> None:
    """Write a list of welds to a JSON file."""
    path = Path(path)
    data = [_weld_to_dict(w) for w in welds]
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def to_csv(welds: list[PointWeld | LinearWeld], path: str | Path) -> None:
    """Write a list of welds to a CSV file.

    Point welds produce one row each. Linear welds produce one row per cell.
    """
    path = Path(path)
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["type", "weld_id", "row", "col"])
        for weld in welds:
            if isinstance(weld, PointWeld):
                writer.writerow(["point", weld.weld_id, weld.row, weld.col])
            else:
                for r, c in weld.cells:
                    writer.writerow(["linear", weld.weld_id, r, c])


def to_xlsx(welds: list[PointWeld | LinearWeld], path: str | Path) -> None:
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
            for r, c in weld.cells:
                ws.append(["linear", weld.weld_id, r, c])

    wb.save(path)
