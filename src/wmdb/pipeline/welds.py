"""Weld extraction from WMDB Pipeline documents — placeholder."""

from __future__ import annotations

from typing import Any

from wmdb.types import LinearWeld, PointWeld


def get_point_welds(doc: dict[str, Any]) -> list[PointWeld]:
    """Extract point welds from a WMDB Pipeline document.

    Not yet implemented — the pipeline drawing standard has not been defined.
    """
    raise NotImplementedError("Pipeline weld extraction is not yet implemented")


def get_linear_welds(doc: dict[str, Any]) -> list[LinearWeld]:
    """Extract linear welds from a WMDB Pipeline document.

    Not yet implemented — the pipeline drawing standard has not been defined.
    """
    raise NotImplementedError("Pipeline weld extraction is not yet implemented")
