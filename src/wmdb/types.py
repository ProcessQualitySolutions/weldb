"""Shared weld types used across all WMDB standards."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class PointWeld:
    """A single point weld extracted from the current map."""

    weld_id: str
    row: int
    col: int


@dataclass
class LinearWeld:
    """A linear weld that spans one or more grid cells."""

    weld_id: str
    cells: list[tuple[int, int]] = field(default_factory=list)
