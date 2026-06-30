"""weldb — Weld Map Database for boiler repair (.weldb files).

A single .weldb YAML file is both the 2D weld map drawing and the
authoritative static weld record for a boiler repair panel.

Usage:
    import weldb

    doc = weldb.load("N5.weldb")
    welds = weldb.get_point_welds(doc)
    weldb.render_pdf("N5.weldb")
"""

from weldb.document import (
    add_revision,
    custom_field_getter,
    custom_field_setter,
    load,
    save,
)
from weldb.export import to_csv, to_json, to_xlsx
from weldb.render import render_monospace, render_pdf
from weldb.models import AreaWeld, LinearWeld, PointWeld
from weldb.weld_log import WELD_ID_SEPARATOR, build_weld_log, prefix_weld_id
from weldb.welds import (
    get_area_welds,
    get_linear_welds,
    get_point_welds,
    resolve_weld_properties,
)

__version__ = "0.1.0"

__all__ = [
    "load",
    "save",
    "add_revision",
    "custom_field_getter",
    "custom_field_setter",
    "get_point_welds",
    "get_linear_welds",
    "get_area_welds",
    "resolve_weld_properties",
    "render_monospace",
    "render_pdf",
    "build_weld_log",
    "prefix_weld_id",
    "WELD_ID_SEPARATOR",
    "to_json",
    "to_csv",
    "to_xlsx",
    "PointWeld",
    "LinearWeld",
    "AreaWeld",
]
