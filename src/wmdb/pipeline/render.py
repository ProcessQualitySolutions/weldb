"""Rendering of WMDB Pipeline documents — placeholder."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def render_monospace(doc: dict[str, Any], col_width: int = 8) -> str:
    """Render a WMDB Pipeline document as monospace text.

    Not yet implemented — the pipeline drawing standard has not been defined.
    """
    raise NotImplementedError("Pipeline rendering is not yet implemented")


def render_pdf(source_path: str | Path) -> Path:
    """Render a .weldp file to PDF.

    Not yet implemented — the pipeline drawing standard has not been defined.
    """
    raise NotImplementedError("Pipeline PDF rendering is not yet implemented")
