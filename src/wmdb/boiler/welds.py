"""Weld extraction from WMDB Boiler documents."""

from __future__ import annotations

from typing import Any

from wmdb.exceptions import (
    ConflictingWeldIdError,
    DuplicatePointWeldInViewError,
    EmbeddedSpecialCharError,
)
from wmdb.types import AreaWeld, LinearWeld, PointWeld

WELD_PREFIXES = ("*", "_", "@")

Grid = list[list[str]]


def _current_views(doc: dict[str, Any]) -> list[dict[str, Any]]:
    """Return the views from the latest (last) map in the document."""
    maps = doc["maps"]
    if not maps:
        raise ValueError("Document has no maps")
    return maps[-1]["views"]


def _validate_grid(grid: Grid) -> None:
    """Check every cell for embedded *, _, or @ characters."""
    for r, row in enumerate(grid):
        for c, cell in enumerate(row):
            if not cell or not cell.strip():
                continue
            if cell[0] not in WELD_PREFIXES:
                if "*" in cell or "_" in cell or "@" in cell:
                    raise EmbeddedSpecialCharError(cell, r, c)


def _validate_no_conflicting_ids(views: list[dict[str, Any]]) -> None:
    """Ensure no two weld types share the same base ID.

    For example, *T205 and _T205 both have base ID "T205" and would collide
    when the prefix is stripped for weld log export.
    """
    seen: dict[str, str] = {}  # base_id -> first original cell

    for view in views:
        for row in view["grid"]:
            for cell in row:
                if not cell or cell[0] not in WELD_PREFIXES:
                    continue
                base_id = cell[1:]
                existing = seen.get(base_id)
                if existing is not None and existing[0] != cell[0]:
                    raise ConflictingWeldIdError(base_id, existing, cell)
                seen[base_id] = cell


def get_point_welds(doc: dict[str, Any]) -> list[PointWeld]:
    """Extract all point welds from the current (latest) map in a WMDB Boiler document.

    Always operates on the last map in the maps array. Historical maps
    never produce welds.

    Point welds are deduplicated across views — each unique weld ID is returned once.
    Uses the position from the first view in which it appears.

    Raises DuplicatePointWeldInViewError if any point weld ID appears more than once
    within a single view's grid.
    Raises ConflictingWeldIdError if two weld types share the same base ID.
    Raises EmbeddedSpecialCharError if *, _, or @ appears mid-string in any cell.
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

    Raises ConflictingWeldIdError if two weld types share the same base ID.
    Raises EmbeddedSpecialCharError if *, _, or @ appears mid-string in any cell.
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


def get_area_welds(doc: dict[str, Any]) -> list[AreaWeld]:
    """Extract all area welds from the current (latest) map in a WMDB Boiler document.

    Always operates on the last map in the maps array. Historical maps
    never produce welds.

    Area welds are collected across all views. If the same area weld ID appears
    in multiple views, cells from all views are combined.

    Raises ConflictingWeldIdError if two weld types share the same base ID.
    Raises EmbeddedSpecialCharError if *, _, or @ appears mid-string in any cell.
    """
    views = _current_views(doc)
    _validate_no_conflicting_ids(views)
    groups: dict[str, list[tuple[int, int]]] = {}

    for view in views:
        grid = view["grid"]
        _validate_grid(grid)

        for r, row in enumerate(grid):
            for c, cell in enumerate(row):
                if cell.startswith("@"):
                    groups.setdefault(cell, []).append((r, c))

    return [AreaWeld(weld_id=wid, cells=locs) for wid, locs in groups.items()]


# Fields that are never inherited by welds.
_NON_INHERITABLE = {"maps", "weld_overrides"}


def resolve_weld_properties(doc: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Resolve effective properties for each weld in the current map.

    Returns a dict mapping weld_id (e.g., ``*250T``, ``_A``) to its resolved
    properties dict.

    Resolution order (most specific wins):

    1. **Top-level fields** — all string/number values (the baseline).
    2. **Type-level override** — ``point`` or ``linear`` key in ``weld_overrides``.
    3. **Weld-specific override** — weld ID key in ``weld_overrides``.
    """
    # 1. Collect inheritable top-level fields (strings and numbers only).
    baseline: dict[str, Any] = {}
    for k, v in doc.items():
        if k in _NON_INHERITABLE:
            continue
        if isinstance(v, (str, int, float)):
            baseline[k] = v

    overrides = doc.get("weld_overrides") or {}
    type_overrides = {
        "*": overrides.get("point") or {},
        "_": overrides.get("linear") or {},
        "@": overrides.get("area") or {},
    }

    # Gather all weld IDs from the current map.
    views = _current_views(doc)
    weld_ids: set[str] = set()
    for view in views:
        for row in view["grid"]:
            for cell in row:
                if cell and cell[0] in WELD_PREFIXES:
                    weld_ids.add(cell)

    result: dict[str, dict[str, Any]] = {}
    for wid in weld_ids:
        props = dict(baseline)
        # 2. Type-level override.
        props.update(type_overrides.get(wid[0], {}))
        # 3. Weld-specific override.
        specific = overrides.get(wid)
        if specific:
            props.update(specific)
        result[wid] = props

    return result
