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
    dumps,
    load,
    loads,
    save,
)
from weldb.export import to_csv, to_json, to_xlsx
from weldb.panel import archive_panel, derived_artifact_paths, save_panel
from weldb.render import (
    first_view_weld_boxes,
    render_monospace,
    render_pdf,
    render_pdf_bytes,
    render_revision_history_pdf,
    render_revision_history_pdf_bytes,
    weld_canvas_boxes,
    weld_positions,
    weld_positions_from_doc,
)
from weldb.models import AreaWeld, LinearWeld, PointWeld
from weldb.validation import ValidationIssue, validate_files, validate_project
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
    "loads",
    "save",
    "dumps",
    "add_revision",
    "save_panel",
    "archive_panel",
    "derived_artifact_paths",
    "custom_field_getter",
    "custom_field_setter",
    "get_point_welds",
    "get_linear_welds",
    "get_area_welds",
    "resolve_weld_properties",
    "render_monospace",
    "render_pdf",
    "render_pdf_bytes",
    "render_revision_history_pdf",
    "render_revision_history_pdf_bytes",
    "weld_positions",
    "weld_positions_from_doc",
    "first_view_weld_boxes",
    "weld_canvas_boxes",
    "build_weld_log",
    "prefix_weld_id",
    "WELD_ID_SEPARATOR",
    "validate_project",
    "validate_files",
    "ValidationIssue",
    "to_json",
    "to_csv",
    "to_xlsx",
    "PointWeld",
    "LinearWeld",
    "AreaWeld",
]
