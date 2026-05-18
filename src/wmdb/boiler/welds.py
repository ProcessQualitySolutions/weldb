"""Weld extraction from WMDB Boiler documents."""

from __future__ import annotations

from typing import Any

from wmdb.exceptions import (
    ConflictingWeldIdError,
    DuplicatePointWeldInViewError,
    EmbeddedSpecialCharError,
)
from wmdb.types import LinearWeld, PointWeld

Grid = list[list[str]]


def _current_views(doc: dict[str, Any]) -> list[dict[str, Any]]:
    """Return the views from the latest (last) map in the document."""
    maps = doc["maps"]
    if not maps:
        raise ValueError("Document has no maps")
    return maps[-1]["views"]


def _validate_grid(grid: Grid) -> None:
    """Check every cell for embedded * or _ characters."""
    for r, row in enumerate(grid):
        for c, cell in enumerate(row):
            if not cell or not cell.strip():
                continue
            if cell[0] not in ("*", "_"):
                if "*" in cell or "_" in cell:
                    raise EmbeddedSpecialCharError(cell, r, c)


def _validate_no_conflicting_ids(views: list[dict[str, Any]]) -> None:
    """Ensure no point weld and linear weld share the same base ID.

    For example, *T205 and _T205 both have base ID "T205" and would collide
    when the prefix is stripped for weld log export.
    """
    point_ids: dict[str, str] = {}  # base_id -> original cell
    linear_ids: dict[str, str] = {}  # base_id -> original cell

    for view in views:
        for row in view["grid"]:
            for cell in row:
                if cell.startswith("*"):
                    point_ids[cell[1:]] = cell
                elif cell.startswith("_"):
                    linear_ids[cell[1:]] = cell

    for base_id in point_ids:
        if base_id in linear_ids:
            raise ConflictingWeldIdError(base_id, point_ids[base_id], linear_ids[base_id])


def get_point_welds(doc: dict[str, Any]) -> list[PointWeld]:
    """Extract all point welds from the current (latest) map in a WMDB Boiler document.

    Always operates on the last map in the maps array. Historical maps
    never produce welds.

    Point welds are deduplicated across views — each unique weld ID is returned once.
    Uses the position from the first view in which it appears.

    Raises DuplicatePointWeldInViewError if any point weld ID appears more than once
    within a single view's grid.
    Raises ConflictingWeldIdError if a point weld and linear weld share the same base ID.
    Raises EmbeddedSpecialCharError if * or _ appears mid-string in any cell.
    """
    views = _current_views(doc)
    _validate_no_conflicting_ids(views)
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

    Raises ConflictingWeldIdError if a point weld and linear weld share the same base ID.
    Raises EmbeddedSpecialCharError if * or _ appears mid-string in any cell.
    """
    views = _current_views(doc)
    _validate_no_conflicting_ids(views)
    groups: dict[str, list[tuple[int, int]]] = {}

    for view in views:
        grid = view["grid"]
        _validate_grid(grid)

        for r, row in enumerate(grid):
            for c, cell in enumerate(row):
                if cell.startswith("_"):
                    groups.setdefault(cell, []).append((r, c))

    return [LinearWeld(weld_id=wid, cells=locs) for wid, locs in groups.items()]
