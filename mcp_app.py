"""weldb MCP Server — AI-assisted weld map management (stateless, logic-only).

This server is a **pure logic and reference resource** for an AI agent. It holds
NO project state and writes NO project files: every tool takes the ``.weldb``
content it needs as input and returns generated content (YAML/CSV/JSON text, or a
PDF as an embedded resource) for the agent to save on the user's own machine. The
agent owns all local file I/O — creating, reading, listing, moving, and deleting
``.weldb``/CSV/PDF files in the user's project folder.

The only files the server reads are its own bundled, read-only reference assets:
the specification ``.md`` documents and the worked-example ``.weldb`` catalog.
This lets the server be hosted online as a lightweight, stateless service.

Transports:
  python mcp_app.py                 # stdio (default) — one local client
  python mcp_app.py remote          # streamable-HTTP — many concurrent sessions
  mcp run mcp_app.py                # stdio via the mcp CLI

See ``main()`` for the remote flags (--host/--port/--path/--stateless/
--json-response/--log-level).
"""

from __future__ import annotations

import argparse
import base64
import csv
import datetime
import io
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from weldb import (
    custom_field_setter,
    dumps,
    get_area_welds,
    get_linear_welds,
    get_point_welds,
    loads,
    prefix_weld_id,
    render_pdf_bytes,
    render_revision_history_pdf_bytes,
    resolve_weld_properties,
    weld_positions_data,
)

# ---------------------------------------------------------------------------
# Configuration — bundled, read-only reference assets only
# ---------------------------------------------------------------------------
#
# The server ships two read-only asset trees, both anchored to THIS file's
# location (not the working directory) so they resolve no matter where or how the
# server is launched, and no matter which machine hosts it:
#   SPEC_DIR     — the standards / specification .md files (drawing_spec, naming
#                  conventions, philosophy) served by list_docs / read_doc.
#   EXAMPLES_DIR — the worked-example .weldb catalog browsed by list_examples /
#                  list_example_files / read_example_file / render_example.
# The server never writes into these (or anywhere else): it is stateless.
CODE_DIR = Path(__file__).resolve().parent
SPEC_DIR = CODE_DIR
EXAMPLES_DIR = CODE_DIR / "examples"

mcp = FastMCP(
    "weldb",
    instructions=(
        "You are a weld map database assistant. You help users create and manage "
        "boiler panel weld maps (.weldb files).\n\n"
        "HOW THIS SERVER WORKS — IMPORTANT: This server is stateless logic only. "
        "It never reads or writes files in the user's project; YOU own all local "
        "file I/O. The tools take .weldb *content* as input and return generated "
        "*content* — .weldb YAML, CSV, or weld-position JSON as text, and PDFs as "
        "an attached resource. After calling a tool, write the returned content to "
        "the user's project folder yourself. Text outputs (create_panel's YAML, "
        "CSV, weld-position JSON) come back as text — write them to the given "
        "filename directly.\n\n"
        "STORING PDFs: the render tools return the PDF as base64 text in a `data` "
        "field, alongside its `filename` (render_example returns one such entry per "
        "PDF under `files`). To keep a PDF, decode its `data` and write the raw "
        "bytes to `filename` in the user's project folder — a BINARY write (e.g. "
        "Python `pathlib.Path(filename).write_bytes(base64.b64decode(data))`). "
        "Never save the base64 text itself, and never write a PDF as UTF-8 text.\n\n"
        "To list, read, move (archive/quarantine), or delete panels, use your own "
        "filesystem tools on the user's project folder — the server does not do "
        "this for you.\n\n"
        "The bundled specification documents (list_docs / read_doc) and the worked "
        "example catalog (list_examples / list_example_files / read_example_file / "
        "render_example) are the server's own read-only references — read them to "
        "learn the .weldb format and how to lay out a weld map before constructing "
        "one.\n\n"
        "When the user asks to create a panel, gather the required information "
        "through conversation before calling create_panel. Required: panel_name, "
        "tube_mtrl, tube_od, tube_wall, units, elevation, tube_start, tube_end. To "
        "pick the panel name, read the existing .weldb files in the user's project "
        "folder and pass their names to suggest_panel_name. Always confirm "
        "parameters with the user before creating. To learn how to lay out a weld "
        "map for a particular situation (adjacent, stacked, or overlapping panels, "
        "clips, ports, dutchman repairs, etc.), browse the worked examples first."
    ),
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

WALL_CODES = [
    "WLS", "ELS", "NTB", "STB", "NBN", "SBN", "ND", "SD",  # directional disambiguations
    "NE", "NW", "SE", "SW",  # corners
    "LS", "US", "TB", "BN",  # features
    "N", "S", "E", "W", "T", "F", "H", "D",  # single-letter walls
]
_WALL_RE = re.compile(r"^(" + "|".join(WALL_CODES) + r")(\d+)$")

# Allowed unit systems (see drawing_spec.md).
VALID_UNITS = ["mm", "ft_in", "in", "dec_in", "dec_ft"]


def _pdf_save_note(filename: str, data_field: str = "data") -> str:
    """One-line instruction telling the agent how to persist a base64 PDF field.

    ``data_field`` names the field that carries the base64 (``data`` for the
    single-PDF tools, ``files[].data`` for render_example).
    """
    return (
        f"HOW TO STORE THIS PDF: the `{data_field}` field is the PDF encoded as "
        f"base64. Decode it and write the raw bytes to `{filename}` in the user's "
        "project folder — a BINARY write (e.g. Python: `import base64, pathlib; "
        f"pathlib.Path('{filename}').write_bytes(base64.b64decode(data))`). Do NOT "
        "save the base64 text itself, and do not write the PDF as UTF-8 text."
    )


def _pdf_payload(filename: str, data: bytes) -> dict[str, Any]:
    """Represent a rendered PDF as a plain base64 text field (never a file).

    The server is stateless and writes nothing: a rendered PDF is returned as
    ``data`` (a base64 ``application/pdf`` string) for the agent to decode and
    save into the user's project folder as ``filename``.
    """
    return {
        "filename": filename,
        "mime_type": "application/pdf",
        "encoding": "base64",
        "data": base64.b64encode(data).decode("ascii"),
    }


def _list_weldb_files(directory: Path) -> list[Path]:
    """List .weldb files in a directory (used only for the bundled examples)."""
    return sorted(directory.glob("*.weldb"))


def _list_example_dirs() -> list[Path]:
    """List the example scenario subfolders under examples/ (sorted)."""
    if not EXAMPLES_DIR.is_dir():
        return []
    return sorted(p for p in EXAMPLES_DIR.iterdir() if p.is_dir())


def _first_comment_line(path: Path) -> str:
    """Return the first leading ``#`` comment line of a file (without the '#').

    Used to surface a one-line description for an example .weldb file. Returns
    an empty string if the file has no leading comment.
    """
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                stripped = line.strip()
                if not stripped:
                    continue
                if stripped.startswith("#"):
                    return stripped.lstrip("#").strip()
                return ""  # first non-blank line is not a comment
    except OSError:
        pass
    return ""


def _resolve_example_path(example: str, filename: str | None = None) -> Path | None:
    """Resolve an example folder (and optional file) safely under examples/.

    Returns the resolved path, or None if it escapes examples/ or does not exist.
    """
    base = EXAMPLES_DIR.resolve()
    target = EXAMPLES_DIR / example
    if filename is not None:
        target = target / filename
    resolved = target.resolve()
    # Guard against path traversal (e.g., '../').
    if resolved != base and base not in resolved.parents:
        return None
    return resolved if resolved.exists() else None


def _next_panel_name(existing_panels: list[str] | None, wall: str) -> str:
    """Next sequential panel name for ``wall``, given the existing panel names.

    ``existing_panels`` is the list of panel names/stems already in the user's
    project (e.g. ``["N5", "N6", "W1"]``) — the agent supplies these from the
    files it sees. Names that do not match ``wall`` are ignored.
    """
    existing_nums: list[int] = []
    for name in existing_panels or []:
        stem = Path(str(name)).stem  # tolerate 'N5' or 'N5.weldb'
        m = _WALL_RE.match(stem)
        if m and m.group(1) == wall:
            existing_nums.append(int(m.group(2)))
    return f"{wall}{max(existing_nums, default=0) + 1}"


def _column_letters(i: int) -> str:
    """Spreadsheet-style column label for a zero-based index (0->A, 25->Z, 26->AA)."""
    letters = ""
    i += 1
    while i > 0:
        i, rem = divmod(i - 1, 26)
        letters = chr(65 + rem) + letters
    return letters


def _build_grid(tube_start: int, tube_end: int) -> list[list[str]]:
    """Build a basic hot-side grid for a tube range.

    Layout: membrane columns between each tube, with outer membranes on
    both edges. Top row has top welds, bottom row has bottom welds,
    middle rows are empty.
    """
    tubes = list(range(tube_start, tube_end + 1))
    num_tubes = len(tubes)
    # Membrane labels: _A, _B, ... _Z, _AA, _AB, ... (spreadsheet-style, so a
    # panel with more than 26 membranes stays alphabetic instead of spilling
    # into '_[', '_\\', '__' etc.).
    num_membranes = num_tubes + 1
    membrane_labels = [f"_{_column_letters(i)}" for i in range(num_membranes)]

    cols = num_membranes + num_tubes  # alternating membrane, tube, membrane...
    top_row: list[str] = []
    bottom_row: list[str] = []
    tube_idx = 0
    mem_idx = 0
    for c in range(cols):
        if c % 2 == 0:
            # Membrane column
            top_row.append(membrane_labels[mem_idx])
            bottom_row.append(membrane_labels[mem_idx])
            mem_idx += 1
        else:
            # Tube column
            top_row.append(f"*T{tubes[tube_idx]}")
            bottom_row.append(f"*B{tubes[tube_idx]}")
            tube_idx += 1

    # Middle rows (4 empty rows)
    empty_row = [""] * cols
    grid = [top_row]
    for _ in range(4):
        grid.append(list(empty_row))
    grid.append(bottom_row)

    return grid


def _build_cold_side_grid(hot_grid: list[list[str]]) -> list[list[str]]:
    """Build an empty cold-side grid matching the hot-side dimensions."""
    rows = len(hot_grid)
    cols = len(hot_grid[0]) if hot_grid else 0
    return [[""] * cols for _ in range(rows)]


# ---------------------------------------------------------------------------
# CSV generation (in-memory — returns text, never writes files)
# ---------------------------------------------------------------------------

# Resolved-property keys that are identity columns already carried by the weld
# row, so they are not repeated as property columns in the CSV export.
_PROP_EXCLUDE = {"panel_name"}


def _weld_props(props_by_id: dict[str, dict[str, Any]], cell: str) -> dict[str, Any]:
    """Effective (panel baseline + type/weld override) properties for a weld cell."""
    props = props_by_id.get(cell, {})
    return {k: v for k, v in props.items() if k not in _PROP_EXCLUDE}


def _weld_csv_text(rows: list[dict[str, Any]], id_cols: list[str]) -> str:
    """Render weld ``rows`` to CSV text with identity + property columns.

    ``id_cols`` are the fixed leading columns; every other key seen across
    ``rows`` (resolved panel properties and weld overrides) is appended as a
    property column in first-seen order. Rows missing a property leave it blank.
    """
    prop_cols: list[str] = []
    for row in rows:
        for key in row:
            if key not in id_cols and key not in prop_cols:
                prop_cols.append(key)
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=id_cols + prop_cols, restval="")
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue()


def _build_weld_csvs(panels: list[str]) -> dict[str, Any]:
    """Build the three weld CSVs (as text) from a list of .weldb *contents*.

    Each item of ``panels`` is the full text of one ``.weldb`` file. Extraction
    goes through the library extractors, so a file the library rejects
    (conflicting IDs, duplicate point welds, cross-file duplicate) is reported and
    skipped, never partially included. Returns a dict with the three CSV texts and
    a skip report; the agent writes the CSVs into the user's project folder.
    """
    point_rows: list[dict[str, Any]] = []
    linear_rows: list[dict[str, Any]] = []
    area_rows: list[dict[str, Any]] = []

    seen_points: dict[str, str] = {}  # prefixed_id -> source panel
    skipped: list[str] = []

    for idx, content in enumerate(panels):
        label = f"panel #{idx + 1}"
        try:
            doc = loads(content)
            panel_name = doc["panel_name"]
            label = f"{panel_name}.weldb"
            source = f"{panel_name}.weldb"
            props_by_id = resolve_weld_properties(doc)

            point_welds = get_point_welds(doc)
            linear_welds = get_linear_welds(doc)
            area_welds = get_area_welds(doc)

            # Detect cross-file point-weld duplicates before committing any of
            # this file's rows, so a rejected file leaves the accumulators clean.
            file_point_ids: dict[str, str] = {}
            for pw in point_welds:
                prefixed_id = prefix_weld_id(panel_name, pw.weld_id)
                if prefixed_id in seen_points:
                    raise ValueError(
                        f"Duplicate weld '{prefixed_id}' also in {seen_points[prefixed_id]}"
                    )
                file_point_ids[pw.weld_id] = prefixed_id

            new_point_rows = [
                {
                    "panel": panel_name,
                    "weld_id": file_point_ids[pw.weld_id],
                    "source": source,
                    **_weld_props(props_by_id, pw.weld_id),
                }
                for pw in point_welds
            ]
            new_linear_rows = [
                {
                    "panel": panel_name,
                    "weld_id": prefix_weld_id(panel_name, lw.weld_id),
                    "source": source,
                    **_weld_props(props_by_id, lw.weld_id),
                }
                for lw in linear_welds
            ]
            new_area_rows = [
                {
                    "panel": panel_name,
                    "weld_id": prefix_weld_id(panel_name, aw.weld_id),
                    "source": source,
                    **_weld_props(props_by_id, aw.weld_id),
                }
                for aw in area_welds
            ]

            for prefixed_id in file_point_ids.values():
                seen_points[prefixed_id] = source
            point_rows.extend(new_point_rows)
            linear_rows.extend(new_linear_rows)
            area_rows.extend(new_area_rows)
        except Exception as exc:  # noqa: BLE001 — report and skip, never abort
            skipped.append(f"{label}: {exc}")

    id_cols = ["panel", "weld_id", "source"]
    files = [
        {"filename": "point_welds.csv", "content": _weld_csv_text(point_rows, id_cols)},
        {"filename": "linear_welds.csv", "content": _weld_csv_text(linear_rows, id_cols)},
        {"filename": "area_welds.csv", "content": _weld_csv_text(area_rows, id_cols)},
    ]
    return {
        "files": files,
        "counts": {
            "point_welds": len(point_rows),
            "linear_welds": len(linear_rows),
            "area_welds": len(area_rows),
        },
        "skipped": skipped,
        "note": (
            "Write each file's `content` to `filename` in the user's project "
            "folder. Skipped panels were not included — fix them and re-run."
        ),
    }


# ---------------------------------------------------------------------------
# Tools — panel generation & inspection (content in, content out)
# ---------------------------------------------------------------------------


@mcp.tool()
def summarize_panels(panels: list[str]) -> str:
    """Validate and summarize a set of .weldb panels supplied as content.

    Because the server holds no project state, pass the *contents* of the .weldb
    files you have read from the user's project folder (one string per file).
    Each is loaded with the library's validation and summarized (panel name,
    material, OD, wall, units, latest rev, point-weld count). A file that fails to
    load is listed with its error instead of aborting the whole summary.
    """
    if not panels:
        return "No panel contents provided. Read the user's .weldb files and pass them in."

    lines = [f"Panels ({len(panels)}):", ""]
    for idx, content in enumerate(panels):
        try:
            doc = loads(content)
            maps = doc.get("maps", [])
            latest = maps[-1] if maps else {}
            views = latest.get("views", [])
            point_count = sum(
                1
                for v in views
                for row in v.get("grid", [])
                for cell in row
                if cell.startswith("*")
            )
            lines.append(
                f"  {doc.get('panel_name', f'#{idx + 1}'):8s}  "
                f"mtrl={doc.get('tube_mtrl', '?')}  "
                f"od={doc.get('tube_od', '?')}  "
                f"wall={doc.get('tube_wall', '?')}  "
                f"units={doc.get('units', '?')}  "
                f"rev={latest.get('rev', '?')}  "
                f"welds={point_count}"
            )
        except Exception as exc:  # noqa: BLE001 — report, don't abort the summary
            lines.append(f"  panel #{idx + 1}  <error: {exc}>")
    return "\n".join(lines)


@mcp.tool()
def suggest_panel_name(wall_code: str, existing_panels: list[str] | None = None) -> str:
    """Suggest the next panel name for a given wall code.

    Use this after determining which wall the user is referring to (e.g. 'west
    wall' -> wall_code='W'). Pass ``existing_panels`` = the names of the .weldb
    panels already in the user's project folder (stems like ``N5`` or filenames
    like ``N5.weldb``, either works) so the number continues the sequence; omit it
    to start at 1.

    Valid wall codes are the entries in WALL_CODES (single-letter walls N, S, E,
    W, T, F, H, D; features LS, US, TB, BN; corners NE, NW, SE, SW; and the
    directional disambiguations WLS, ELS, NTB, STB, NBN, SBN, ND, SD).
    """
    wall_code = wall_code.upper()
    if wall_code not in WALL_CODES:
        return f"Unknown wall code '{wall_code}'. Valid codes: {', '.join(WALL_CODES)}"
    name = _next_panel_name(existing_panels, wall_code)
    return f"Next available panel name for {wall_code} wall: {name}"


@mcp.tool()
def create_panel(
    panel_name: str,
    tube_mtrl: str,
    tube_od: float,
    tube_wall: float,
    units: str,
    elevation: str,
    tube_start: int,
    tube_end: int,
    elevation_at: str = "",
    updated_by: str = "mcp",
    comments: str = "Initial weld map layout",
    custom_fields: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Generate a new .weldb panel with hot_side and cold_side views.

    Returns the panel as text for YOU to save — the server writes nothing. The
    result carries ``filename`` (``<panel_name>.weldb``) and ``content`` (the YAML
    to write into the user's project folder).

    Before calling this tool, you MUST:
    1. Determine the correct panel_name using the panel naming convention (wall
       code + next sequential number). Read the user's existing .weldb files and
       pass their names to suggest_panel_name.
    2. Confirm tube_mtrl, tube_od, tube_wall, units, and elevation with the user.
    3. Know the tube range (tube_start and tube_end inclusive).

    The layout has membrane welds between tubes, point welds at tube top/bottom,
    and an empty cold-side view.

    Args:
        panel_name: Panel identifier (e.g., W3, N5, LS2). Must match wall code + number.
        tube_mtrl: Tube material spec (e.g., SA-210 A1).
        tube_od: Tube outside diameter.
        tube_wall: Tube wall thickness.
        units: One of: mm, ft_in, in, dec_in, dec_ft.
        elevation: Where the panel sits — a free-form dimension (e.g. '1850 in')
            or a scaffold floor level (e.g. 'Scaffold L3'). Required, non-empty.
        tube_start: First tube number (inclusive).
        tube_end: Last tube number (inclusive).
        elevation_at: Optional note for what the elevation refers to (e.g. 'top').
        updated_by: Author of the revision.
        comments: Revision comment.
        custom_fields: Optional dict of extra top-level fields (e.g., client, job_number).

    Returns a dict with ``filename``, ``content``, and a ``summary`` message.
    """
    # Validate panel name format
    m = _WALL_RE.match(panel_name)
    if not m:
        return {
            "error": (
                f"Invalid panel name '{panel_name}'. Expected format: "
                f"<wall_code><number> (e.g., N5, W3, LS2). "
                f"Valid wall codes: {', '.join(WALL_CODES)}"
            )
        }

    if units not in VALID_UNITS:
        return {"error": f"Invalid units '{units}'. Must be one of: {', '.join(VALID_UNITS)}."}

    if not elevation.strip():
        return {
            "error": "elevation is required and must not be empty (e.g. '1850 in' or 'Scaffold L3')."
        }

    if tube_start > tube_end:
        return {"error": f"tube_start ({tube_start}) must be <= tube_end ({tube_end})."}

    # Build grids
    hot_grid = _build_grid(tube_start, tube_end)
    cold_grid = _build_cold_side_grid(hot_grid)

    doc: dict[str, Any] = {
        "panel_name": panel_name,
        "tube_mtrl": tube_mtrl,
        "tube_od": tube_od,
        "tube_wall": tube_wall,
        "units": units,
        "elevation": elevation,
    }
    if elevation_at.strip():
        doc["elevation_at"] = elevation_at

    if custom_fields:
        for k, v in custom_fields.items():
            try:
                custom_field_setter(doc, k, v)
            except ValueError as exc:
                return {
                    "error": (
                        f"Invalid custom field '{k}': {exc} Pass reserved fields "
                        "(panel_name, units, elevation, etc.) as their own arguments, "
                        "not in custom_fields."
                    )
                }

    doc["maps"] = [
        {
            "rev": "R0",
            "date": datetime.date.today().isoformat(),
            "updated_by": updated_by,
            "comments": comments,
            "views": [
                {"name": "hot_side", "grid": hot_grid},
                {"name": "cold_side", "grid": cold_grid},
            ],
        }
    ]

    # Serialize to text, then round-trip through the loader so this tool never
    # returns content the library would reject.
    content = dumps(doc)
    try:
        loads(content)
    except Exception as exc:  # noqa: BLE001 — surface the failure
        return {"error": f"create_panel produced invalid content: {exc}"}

    num_tubes = tube_end - tube_start + 1
    point_welds = num_tubes * 2
    return {
        "filename": f"{panel_name}.weldb",
        "content": content,
        "summary": (
            f"Generated {panel_name}.weldb — tubes {tube_start}-{tube_end} "
            f"({num_tubes} tubes), {point_welds} point welds, {num_tubes + 1} "
            f"membrane welds, views hot_side + cold_side. Save `content` as "
            f"`{panel_name}.weldb` in the user's project folder."
        ),
    }


@mcp.tool()
def build_weld_csvs(panels: list[str]) -> dict[str, Any]:
    """Build point/linear/area weld CSVs from a set of .weldb panel contents.

    Pass the *contents* of the .weldb files in the user's project folder (one
    string per file). Returns the three CSVs (``point_welds.csv``,
    ``linear_welds.csv``, ``area_welds.csv``) as text under ``files`` — write each
    into the user's project folder. Each weld row carries its effective properties
    (the panel's top-level properties merged with type-level and weld-specific
    overrides). Panels that fail to load or validate are reported under
    ``skipped`` and excluded — fix them and re-run.
    """
    if not panels:
        return {"error": "No panel contents provided. Read the user's .weldb files and pass them in."}
    return _build_weld_csvs(panels)


@mcp.tool()
def extract_weld_positions(
    content: str,
    canvas_w: float | None = None,
    canvas_h: float | None = None,
    include_text: bool = False,
) -> dict[str, Any]:
    """Locate every weld on the panel's rendered PDF, as a JSON coordinate map.

    Use this to find where each weld sits **on the PDF that render_pdf produces**
    — e.g. to drop a pin, highlight, or clickable hotspot onto that drawing. Pass
    the .weldb file's ``content`` (its text); the tool derives the PDF geometry
    from the same layout math render_pdf uses, so no PDF file has to exist. It
    returns the coordinate map as JSON text for you to save (suggested filename
    ``<panel_name>_weld_positions.json``) — the server writes nothing.

    For each weld region the JSON holds a bounding box (upper-left ``x0,y0`` and
    lower-right ``x1,y1``) in the rendered PDF's coordinate space: millimetres,
    origin at the **top-left**, y increasing downward. Page width/height (mm) are
    included so a consumer can map the boxes onto any canvas.

    QC Database pixel conversion: pass ``canvas_w`` and ``canvas_h`` (target canvas
    size in pixels). Each weld then also gets integer ``px0, py0, px1, py1`` pixel
    corners, scaled proportionally from mm (no vertical flip). Omit them to keep
    the output device-independent.

    Args:
        content: The .weldb file's text.
        canvas_w: Optional target canvas width in pixels (enables px output).
        canvas_h: Optional target canvas height in pixels (enables px output).
        include_text: If true, also report plain-text regions (tube numbers,
            annotations), not just welds. Empty regions are never reported.

    Returns a dict with ``filename`` and ``content`` (the JSON text).
    """
    if (canvas_w is None) != (canvas_h is None):
        return {"error": "Provide both canvas_w and canvas_h for pixel output, or neither."}
    if canvas_w is not None and (canvas_w <= 0 or canvas_h <= 0):
        return {"error": "canvas_w and canvas_h must be positive."}

    try:
        doc = loads(content)
    except Exception as exc:  # noqa: BLE001 — surface parse/validation failure
        return {"error": f"Could not parse .weldb content: {exc}"}

    try:
        data = weld_positions_data(
            doc, include_text=include_text, canvas_w=canvas_w, canvas_h=canvas_h
        )
    except ImportError as exc:
        return {"error": f"Weld position extraction unavailable: {exc}"}
    except Exception as exc:  # noqa: BLE001 — surface the failure to the caller
        return {"error": f"Failed to extract weld positions: {exc}"}

    panel_name = data.get("panel_name") or doc.get("panel_name", "panel")
    return {
        "filename": f"{panel_name}_weld_positions.json",
        "content": json.dumps(data, indent=2),
        "note": "Save `content` as `filename` in the user's project folder if you need it persisted.",
    }


# ---------------------------------------------------------------------------
# Tools — PDF rendering (returns the PDF as base64 text; never written server-side)
# ---------------------------------------------------------------------------


@mcp.tool(structured_output=False)
def render_pdf(content: str, color: bool = False) -> dict[str, Any]:
    """Render a panel to a single-sheet vector engineering-drawing PDF.

    Pass the .weldb file's ``content`` (its text). The PDF is returned as base64
    text in the ``data`` field (with ``filename`` = ``<panel_name>.pdf``) for YOU
    to decode and save into the user's project folder — the server writes nothing.
    Decode ``data`` and write the raw bytes to ``filename`` as a BINARY write; see
    the returned ``note``. The sheet has a double-width border; the top 80% holds
    the views (each grid scaled to fill its box, an empty back/cold view mirrored
    from its sibling); a double-width line separates the bottom 20% title block
    (properties, legend and weld tallies, most recent revisions that fit).

    Args:
        content: The .weldb file's text.
        color: When true, grid cells are tinted with light, text-safe colors and
            the legend gains matching swatches. Default renders black-on-white.

    Returns a dict with ``filename``, ``mime_type``, ``encoding`` ("base64"),
    ``data`` (the base64 PDF), plus a ``summary`` and a ``note`` on how to save it.
    Requires the optional fpdf2 dependency (pip install weldb[pdf]).
    """
    try:
        doc = loads(content)
    except Exception as exc:  # noqa: BLE001
        return {"error": f"Could not parse .weldb content: {exc}"}

    try:
        data = render_pdf_bytes(doc, color=color)
    except ImportError as exc:
        return {"error": f"PDF rendering unavailable: {exc}"}
    except Exception as exc:  # noqa: BLE001 — surface the failure to the caller
        return {"error": f"Failed to render PDF: {exc}"}

    panel_name = doc.get("panel_name", "panel")
    filename = f"{panel_name}.pdf"
    kind = "color" if color else "black-and-white"
    payload = _pdf_payload(filename, data)
    payload["summary"] = f"Rendered {filename} ({kind})."
    payload["note"] = _pdf_save_note(filename)
    return payload


@mcp.tool(structured_output=False)
def render_revision_history(content: str) -> dict[str, Any]:
    """Render a panel's full revision history to a standalone PDF.

    Pass the .weldb file's ``content`` (its text). The PDF is returned as base64
    text in the ``data`` field (with ``filename`` = ``<panel_name>_revisions.pdf``)
    for YOU to decode and save — the server writes nothing; see the returned
    ``note``. Lists every revision in a bordered table (Rev, Date, Updated By,
    Comments), oldest to newest, paginated as needed. Unlike the abbreviated
    revision block on the main drawing (capped to what fits), this is the
    complete, unabridged history.

    Returns a dict with ``filename``, ``mime_type``, ``encoding`` ("base64"),
    ``data`` (the base64 PDF), plus a ``summary`` and a ``note`` on how to save it.
    Requires the optional fpdf2 dependency (pip install weldb[pdf]).
    """
    try:
        doc = loads(content)
    except Exception as exc:  # noqa: BLE001
        return {"error": f"Could not parse .weldb content: {exc}"}

    try:
        data = render_revision_history_pdf_bytes(doc)
        n_revs = len(doc.get("maps", []))
    except ImportError as exc:
        return {"error": f"PDF rendering unavailable: {exc}"}
    except Exception as exc:  # noqa: BLE001 — surface the failure to the caller
        return {"error": f"Failed to render revision history: {exc}"}

    panel_name = doc.get("panel_name", "panel")
    filename = f"{panel_name}_revisions.pdf"
    payload = _pdf_payload(filename, data)
    payload["summary"] = f"Rendered {filename} ({n_revs} revision(s))."
    payload["note"] = _pdf_save_note(filename)
    return payload


# ---------------------------------------------------------------------------
# Tools — bundled reference documents (read-only, server-side)
# ---------------------------------------------------------------------------


@mcp.tool()
def list_docs() -> str:
    """List all specification and documentation files (.md) bundled with the server.

    Returns file names and first-line descriptions. Use read_doc to read the full
    content of any document. These are the server's own read-only references.
    """
    md_files = sorted(SPEC_DIR.glob("*.md"))
    if not md_files:
        return "No documentation files found."

    lines = ["Available documentation:", ""]
    for f in md_files:
        first_line = ""
        with open(f, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line.startswith("# "):
                    first_line = line[2:]
                    break
        lines.append(f"  {f.name:40s} {first_line}")
    return "\n".join(lines)


@mcp.tool()
def read_doc(filename: str) -> str:
    """Read the full content of a bundled specification/documentation file.

    Pass the filename (e.g., 'drawing_spec.md', 'weldb_design_philosophy.md',
    'panel_naming_convention.md'). Only .md files bundled with the server are
    accessible.
    """
    if not filename.endswith(".md"):
        return "Only .md files can be read with this tool."

    filepath = SPEC_DIR / filename

    # Prevent path traversal — check this BEFORE exists() so the response never
    # leaks whether an arbitrary path outside the spec dir exists.
    if not filepath.resolve().parent == SPEC_DIR.resolve():
        return "Access denied."

    if not filepath.exists():
        return f"File not found: {filename}. Use list_docs to see available files."

    return filepath.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Tools — bundled example catalog (read-only, server-side reference)
# ---------------------------------------------------------------------------


@mcp.tool()
def list_examples() -> str:
    """List the example arrangements in the bundled examples/ catalog.

    Each subfolder demonstrates a common panel arrangement (e.g., single,
    adjacent, stacked, overlapping) with one or more reference .weldb files.
    Use these as worked examples when constructing a new weld map: pick the
    arrangement that matches what the user is describing, then drill in with
    list_example_files and read_example_file.
    """
    dirs = _list_example_dirs()
    if not dirs:
        return f"No example folders found in {EXAMPLES_DIR}"

    lines = ["Example catalog (examples/):", ""]
    for d in dirs:
        weldb_files = _list_weldb_files(d)
        summary = _first_comment_line(weldb_files[0]) if weldb_files else ""
        header = f"  {d.name}/ ({len(weldb_files)} file{'s' if len(weldb_files) != 1 else ''})"
        lines.append(f"{header}  {summary}".rstrip())
    return "\n".join(lines)


@mcp.tool()
def list_example_files(example: str) -> str:
    """List the files in one example arrangement folder.

    Pass the folder name returned by list_examples (e.g., 'adjacent').
    Returns each .weldb file with its one-line description so you can decide
    which to read in full.
    """
    folder = _resolve_example_path(example)
    if folder is None or not folder.is_dir():
        names = ", ".join(d.name for d in _list_example_dirs()) or "(none)"
        return f"Example '{example}' not found. Available: {names}"

    weldb_files = _list_weldb_files(folder)
    other_files = sorted(
        p for p in folder.iterdir() if p.is_file() and p.suffix != ".weldb"
    )
    if not weldb_files and not other_files:
        return f"Example '{example}' is empty."

    lines = [f"Files in examples/{example}/:", ""]
    for f in weldb_files:
        desc = _first_comment_line(f)
        lines.append(f"  {f.name:16s} {desc}".rstrip())
    for f in other_files:
        lines.append(f"  {f.name}")
    return "\n".join(lines)


@mcp.tool()
def read_example_file(example: str, filename: str) -> str:
    """Read the full text of a file in an example arrangement folder.

    Pass the folder name (e.g., 'stacked') and the file name (e.g.,
    'N5L.weldb'). Returns the raw file contents, including the leading
    comments that explain how the arrangement is laid out — read these to
    learn how to construct a similar weld map.
    """
    filepath = _resolve_example_path(example, filename)
    if filepath is None or not filepath.is_file():
        return (
            f"File '{filename}' not found in example '{example}'. "
            f"Use list_example_files('{example}') to see what's available."
        )
    return filepath.read_text(encoding="utf-8")


@mcp.tool(structured_output=False)
def render_example(example: str, filename: str | None = None, color: bool = False) -> dict[str, Any]:
    """Render bundled example .weldb file(s) to PDF, returned as base64 text.

    The examples catalog is a read-only reference, so the PDFs are returned as
    base64 text (never written to disk). Pass an example folder name and
    optionally a single .weldb file name; if filename is omitted, every .weldb
    file in the folder is rendered. Each rendered PDF appears in ``files`` as
    ``{filename, mime_type, encoding, data}`` where ``data`` is the base64 PDF —
    decode it and write the raw bytes to ``filename`` (a BINARY write) if you want
    to keep it in the user's project folder; see the returned ``note``.

    Requires the optional fpdf2 dependency (pip install weldb[pdf]).
    """
    folder = _resolve_example_path(example)
    if folder is None or not folder.is_dir():
        names = ", ".join(d.name for d in _list_example_dirs()) or "(none)"
        return {"error": f"Example '{example}' not found. Available: {names}"}

    if filename is not None:
        target = _resolve_example_path(example, filename)
        if target is None or not target.is_file():
            return {"error": f"File '{filename}' not found in example '{example}'."}
        targets = [target]
    else:
        targets = _list_weldb_files(folder)
        if not targets:
            return {"error": f"Example '{example}' has no .weldb files to render."}

    files: list[dict[str, Any]] = []
    errors: list[str] = []
    for src in targets:
        try:
            doc = loads(src.read_text(encoding="utf-8"))
            data = render_pdf_bytes(doc, color=color)
        except ImportError as exc:
            return {"error": f"PDF rendering unavailable: {exc}"}
        except Exception as exc:  # noqa: BLE001 — report per-file failures
            errors.append(f"{src.name}: {exc}")
            continue
        files.append(_pdf_payload(f"{src.stem}.pdf", data))

    names = ", ".join(f["filename"] for f in files) or "(none)"
    result: dict[str, Any] = {
        "files": files,
        "summary": f"Rendered {len(files)} PDF(s) from examples/{example}/: {names}.",
        "note": (
            "Each entry in `files` has a base64 `data` field. To keep a PDF, decode "
            "its `data` and write the raw bytes to its `filename` in the user's "
            "project folder — a BINARY write (e.g. Python `pathlib.Path(filename)."
            "write_bytes(base64.b64decode(data))`). Do not save the base64 text itself."
        ),
    }
    if errors:
        result["errors"] = errors
    return result


# ---------------------------------------------------------------------------
# Prompts — guide the AI's conversational behavior
# ---------------------------------------------------------------------------


@mcp.prompt()
def create_panel_workflow() -> str:
    """Guided workflow for creating a new boiler panel from user description."""
    return (
        "The user wants to create a new boiler panel weld map. This server is "
        "stateless — you own all file I/O. Follow these steps:\n\n"
        "1. Read the existing .weldb files in the user's project folder (your own "
        "file tools) so you know what panels exist.\n"
        "2. Call read_doc with 'panel_naming_convention.md' to understand naming rules.\n"
        "3. From the user's description, determine:\n"
        "   - Which wall (N, S, E, W, T, LS, H, TB, etc.)\n"
        "   - The tube range (e.g., tubes 125 to 150)\n"
        "4. Call suggest_panel_name with the wall code and the existing panel names "
        "to get the next available name.\n"
        "5. Ask the user for tube parameters if not already provided:\n"
        "   - tube_mtrl (e.g., SA-210 A1)\n"
        "   - tube_od (e.g., 2.0)\n"
        "   - tube_wall (e.g., 0.15)\n"
        "   - units (e.g., in)\n"
        "   - elevation (e.g., 1850 in, or Scaffold L3)\n"
        "6. Confirm all parameters with the user before calling create_panel.\n"
        "7. Write create_panel's returned `content` to `<panel_name>.weldb` in the "
        "user's project folder, then show the user what was created."
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def _build_arg_parser() -> argparse.ArgumentParser:
    """CLI for choosing the transport and (for remote) its HTTP binding.

    Defaults are read from the environment so the server can be configured with
    no arguments in a container: ``WELDB_HOST``, ``WELDB_PORT``, ``WELDB_PATH``,
    ``WELDB_LOG_LEVEL``.
    """
    parser = argparse.ArgumentParser(
        prog="weldb-mcp",
        description=(
            "weldb MCP server — stateless, logic-only. Runs over stdio by default "
            "(one local client); pass 'remote' to serve many concurrent sessions "
            "over streamable HTTP. The server never reads or writes project files; "
            "the AI agent owns all local file I/O."
        ),
    )
    parser.add_argument(
        "mode",
        nargs="?",
        choices=["stdio", "remote"],
        default="stdio",
        help="Transport to run. 'stdio' (default) for a single local client, "
        "'remote' for a hostable streamable-HTTP server handling multiple sessions.",
    )
    parser.add_argument(
        "--host",
        default=os.environ.get("WELDB_HOST", "127.0.0.1"),
        help="Remote mode: interface to bind (default 127.0.0.1; use 0.0.0.0 to "
        "accept connections from other hosts).",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("WELDB_PORT", "8000")),
        help="Remote mode: TCP port to listen on (default 8000).",
    )
    parser.add_argument(
        "--path",
        default=os.environ.get("WELDB_PATH", "/mcp"),
        help="Remote mode: HTTP path the streamable-HTTP endpoint is served at "
        "(default /mcp).",
    )
    parser.add_argument(
        "--stateless",
        action="store_true",
        help="Remote mode: run stateless HTTP (no per-session state kept between "
        "requests). This server holds no state either way, so this is safe and "
        "ideal behind a load balancer with multiple replicas.",
    )
    parser.add_argument(
        "--json-response",
        action="store_true",
        help="Remote mode: return plain JSON responses instead of SSE streams.",
    )
    parser.add_argument(
        "--log-level",
        default=os.environ.get("WELDB_LOG_LEVEL", "INFO"),
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Logging level (default INFO).",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    """Parse startup arguments and run the server on the selected transport."""
    args = _build_arg_parser().parse_args(argv)

    mcp.settings.log_level = args.log_level

    if args.mode == "stdio":
        mcp.run(transport="stdio")
        return

    # Remote: hostable streamable-HTTP transport with concurrent sessions.
    mcp.settings.host = args.host
    mcp.settings.port = args.port
    mcp.settings.streamable_http_path = args.path
    mcp.settings.stateless_http = args.stateless
    mcp.settings.json_response = args.json_response

    print(
        f"weldb MCP server (remote/streamable-HTTP, stateless logic-only) "
        f"listening on http://{args.host}:{args.port}{args.path}"
        + ("  [stateless-http]" if args.stateless else ""),
        file=sys.stderr,
    )
    mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
