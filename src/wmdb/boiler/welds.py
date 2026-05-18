"""Weld extraction from WMDB Boiler documents."""

from __future__ import annotations

from typing import Any

from wmdb.exceptions import DuplicatePointWeldInViewError, EmbeddedSpecialCharError
from wmdb.types import LinearWeld, PointWeld

Grid = list[list[str]]


def _current_views(doc: dict[str, Any]) -> list[dict[str, Any]]:
    """Return the views from the latest (last) map in the document."""
    maps = doc["maps"]
    if not maps:
        raise ValueError("Document has no maps")
    return maps[-1]["views"]


def _validate_grid(grid: Grid) -> None:
    """Check every cell for embedded * or ^ characters."""
    for r, row in enumerate(grid):
        for c, cell in enumerate(row):
            if not cell or not cell.strip():
                continue
            if cell[0] not in ("*", "^"):
                if "*" in cell or "^" in cell:
                    raise EmbeddedSpecialCharError(cell, r, c)


def get_point_welds(doc: dict[str, Any]) -> list[PointWeld]:
    """Extract all point welds from the current (latest) map in a WMDB Boiler document.

    Always operates on the last map in the maps array. Historical maps
    never produce welds.

    Point welds are deduplicated across views — each unique weld ID is returned once.
    Uses the position from the first view in which it appears.

    Raises DuplicatePointWeldInViewError if any point weld ID appears more than once
    within a single view's grid.
    Raises EmbeddedSpecialCharError if * or ^ appears mid-string in any cell.
    """
    views = _current_views(doc)
    all_welds: dict[str, PointWeld] = {}

    for view in views:
        view_name = view["name"]
        grid = view["grid"]
        _validate_grid(grid)

        seen: dict[str, list[tuple[int, int]]] = {}
        for r, row in enumerate(grid):
            for c, cell in enumerate(row):
                if cell.startswith("*"):
                    seen.setdefault(cell, []).append((r, c))

        for weld_id, locations in seen.items():
            if len(locations) > 1:
                raise DuplicatePointWeldInViewError(weld_id, view_name, locations)

        for weld_id, locations in seen.items():
            if weld_id not in all_welds:
                all_welds[weld_id] = PointWeld(
                    weld_id=weld_id, row=locations[0][0], col=locations[0][1]
                )

    return list(all_welds.values())


def get_linear_welds(doc: dict[str, Any]) -> list[LinearWeld]:
    """Extract all linear welds from the current (latest) map in a WMDB Boiler document.

    Always operates on the last map in the maps array. Historical maps
    never produce welds.

    Linear welds are collected across all views. If the same linear weld ID appears
    in multiple views, cells from all views are combined.

    Raises EmbeddedSpecialCharError if * or ^ appears mid-string in any cell.
    """
    views = _current_views(doc)
    groups: dict[str, list[tuple[int, int]]] = {}

    for view in views:
        grid = view["grid"]
        _validate_grid(grid)

        for r, row in enumerate(grid):
            for c, cell in enumerate(row):
                if cell.startswith("^"):
                    groups.setdefault(cell, []).append((r, c))

    return [LinearWeld(weld_id=wid, cells=locs) for wid, locs in groups.items()]
