"""wmdb.iron — Weld Map Database for structural steel (.weldi files).

This module is a placeholder. The iron drawing standard has not yet been defined.
"""

from wmdb.iron.document import load, save
from wmdb.iron.welds import get_linear_welds, get_point_welds
from wmdb.iron.render import render_monospace, render_pdf
from wmdb.types import LinearWeld, PointWeld

__all__ = [
    "load",
    "save",
    "get_point_welds",
    "get_linear_welds",
    "render_monospace",
    "render_pdf",
    "PointWeld",
    "LinearWeld",
]
