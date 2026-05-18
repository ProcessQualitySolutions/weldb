"""Rendering of WMDB Iron documents — placeholder."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def render_monospace(doc: dict[str, Any], col_width: int = 8) -> str:
    """Render a WMDB Iron document as monospace text.

    Not yet implemented — the iron drawing standard has not been defined.
    """
    raise NotImplementedError("Iron rendering is not yet implemented")


def render_pdf(source_path: str | Path) -> Path:
    """Render a .weldi file to PDF.

    Not yet implemented — the iron drawing standard has not been defined.
    """
    raise NotImplementedError("Iron PDF rendering is not yet implemented")
