"""weldb MCP Server — AI-assisted weld map management.

Provides tools for creating and inspecting boiler weld map panels,
listing existing project files, reading specification documents, and
browsing a catalog of worked example panels organized by arrangement.

Run with:  python mcp_app.py
Or:        mcp run mcp_app.py
"""

from __future__ import annotations

import csv
import datetime
import re
import shutil
import sys
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from weldb import load, prefix_weld_id, resolve_weld_properties, save

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Code-bundled assets (ship with this server, independent of the user's project):
#   SPEC_DIR     — the standards / specification .md files (drawing_spec, naming
#                  conventions, philosophy) served by list_docs / read_doc.
#   EXAMPLES_DIR — the read-only worked-example catalog browsed by the list_example*
#                  / read_example_file / render_example tools.
# Both are anchored to this file's location, NOT the working directory, so they
# resolve correctly no matter where the server is launched from.
CODE_DIR = Path(__file__).resolve().parent
SPEC_DIR = CODE_DIR
EXAMPLES_DIR = CODE_DIR / "examples"

# The AGENT'S PROJECT DIRECTORY: where the .weldb panel files for the current job
# live. This is the user's project folder — NOT the weldb code directory and NOT
# the bundled examples catalog. Every panel tool takes an explicit `project_path`;
# when omitted it falls back to the current working directory, but agents are
# expected to pass the project folder explicitly.
DEFAULT_PROJECT_DIR = Path.cwd()

mcp = FastMCP(
    "weldb",
    instructions=(
        "You are a weld map database assistant. You help users create and manage "
        "boiler panel weld maps (.weldb files).\n\n"
        "PROJECT PATH — IMPORTANT: The weld map panels you create and manage live "
        "in the user's own project folder. Every panel tool takes a `project_path` "
        "argument, and you should pass the path to the user's project directory "
        "(the folder holding their .weldb files for this job). This is NOT the "
        "weldb code/installation directory, and NOT the bundled examples catalog. "
        "If you do not yet know the user's project folder, ask for it before "
        "creating, reading, or listing panels. Omitting project_path falls back to "
        "the server's current working directory, which is usually not what you want.\n\n"
        "The bundled specification documents (list_docs / read_doc) and the worked "
        "example catalog (list_examples / list_example_files / read_example_file / "
        "render_example) are read-only references that ship with the server — they "
        "are separate from the user's project and take no project_path.\n\n"
        "When the user asks to create a panel, gather the required information "
        "through conversation before calling create_panel. Required: panel_name, "
        "tube_mtrl, tube_od, tube_wall, units, elevation, tube_start, tube_end. Use "
        "the panel_naming_convention and existing panels to determine the correct "
        "panel name. Always confirm parameters with the user before creating. To "
        "learn how to lay out a weld map for a particular situation (adjacent, "
        "stacked, or overlapping panels, clips, ports, dutchman repairs, etc.), "
        "browse the worked examples before constructing the grid."
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


def _find_project_dir(path: str | None) -> Path:
    """Resolve the user's project directory from an optional path argument.

    When ``path`` is given it is used (its parent if it points at a file); when
    omitted it falls back to :data:`DEFAULT_PROJECT_DIR` (the current working
    directory). It deliberately does NOT default to the bundled examples catalog
    — panels live in the agent's project folder, which should be passed
    explicitly as ``project_path``.
    """
    if path:
        p = Path(path)
        return p if p.is_dir() else p.parent
    return DEFAULT_PROJECT_DIR


def _resolve_panel_path(base_dir: Path, panel_name: str) -> Path | None:
    """Resolve ``<base_dir>/<panel_name>.weldb``, guarding against path traversal.

    ``panel_name`` must be a bare file stem: any value containing a path
    separator, a parent reference (``..``), or an absolute/drive component is
    rejected (returns ``None``) so a caller-supplied name can never escape
    ``base_dir``. The returned path is not required to exist.
    """
    if not panel_name or panel_name != Path(panel_name).name:
        return None
    target = (base_dir / f"{panel_name}.weldb").resolve()
    if target.parent != base_dir.resolve():
        return None
    return target


def _reject_code_dir(directory: Path) -> str | None:
    """Return an error message if ``directory`` lies inside the static code tree.

    The entire repo folder (this server, the ``weldb`` library, the bundled
    ``examples/`` catalog and the specification ``.md`` files) is a read-only
    resource: the server must never create, move, or overwrite files inside it.
    Any tool that writes checks its target through this guard so a stray
    ``project_path`` pointed at the code directory is refused rather than
    silently mutating the installation.
    """
    d = directory.resolve()
    code = CODE_DIR.resolve()
    if d == code or code in d.parents:
        return (
            f"Refusing to write inside the weldb code directory ({code}). "
            "It is a static resource. Point project_path at the user's own "
            "project folder instead."
        )
    return None


def _quarantine_dir(directory: Path) -> Path:
    return directory / "quarantine"


def _archive_dir(directory: Path) -> Path:
    return directory / "archive"


def _list_weldb_files(directory: Path) -> list[Path]:
    """List .weldb files in directory root (excludes quarantine/ and archive/)."""
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
        with open(path) as fh:
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
    target = (EXAMPLES_DIR / example)
    if filename is not None:
        target = target / filename
    resolved = target.resolve()
    # Guard against path traversal (e.g., '../').
    if resolved != base and base not in resolved.parents:
        return None
    return resolved if resolved.exists() else None


def _next_panel_name(directory: Path, wall: str) -> str:
    """Determine the next sequential panel name for a given wall code."""
    existing_nums: list[int] = []
    for f in _list_weldb_files(directory):
        m = _WALL_RE.match(f.stem)
        if m and m.group(1) == wall:
            existing_nums.append(int(m.group(2)))
    next_num = max(existing_nums, default=0) + 1
    return f"{wall}{next_num}"


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
# Startup — regenerate CSV files
# ---------------------------------------------------------------------------

# Resolved-property keys that are identity columns already carried by the weld
# row, so they are not repeated as property columns in the CSV export.
_PROP_EXCLUDE = {"panel_name"}


def _weld_props(props_by_id: dict[str, dict[str, Any]], cell: str) -> dict[str, Any]:
    """Effective (panel baseline + type/weld override) properties for a weld cell.

    Returns the resolved property dict for ``cell`` (from
    :func:`resolve_weld_properties`) with identity fields already present as CSV
    columns (see :data:`_PROP_EXCLUDE`) stripped out. This is what lets each weld
    row carry the panel's properties and any overrides that apply to it.
    """
    props = props_by_id.get(cell, {})
    return {k: v for k, v in props.items() if k not in _PROP_EXCLUDE}


def _write_weld_csv(path: Path, rows: list[dict[str, Any]], id_cols: list[str]) -> None:
    """Write weld ``rows`` to ``path`` with a header of identity + property columns.

    ``id_cols`` are the fixed leading columns (e.g. panel, weld_id, source); every
    other key seen across ``rows`` — the resolved panel properties and weld
    overrides — is appended as a property column in first-seen order. Rows missing
    a given property leave that cell blank.
    """
    prop_cols: list[str] = []
    for row in rows:
        for key in row:
            if key not in id_cols and key not in prop_cols:
                prop_cols.append(key)
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=id_cols + prop_cols, restval="")
        writer.writeheader()
        writer.writerows(rows)


def _regenerate_all_csv_files(directory: Path) -> str:
    """Load all .weldb files, extract all weld types, write three CSV files.

    Generates:
      - point_welds.csv  — one row per point weld (deduplicated across views)
      - linear_welds.csv — one row per linear weld ID
      - area_welds.csv   — one row per area weld ID

    Each row also carries the weld's effective properties — the panel's top-level
    properties (material, OD, wall, units, elevation, any custom fields) merged
    with the type-level and weld-specific overrides that apply to it (e.g. a
    linear weld's length, an area weld's height). Property columns are the union
    of keys seen across the rows; a weld missing a property leaves it blank.

    Files that raise exceptions are moved to quarantine/.
    Returns a status message.
    """
    guard = _reject_code_dir(directory)
    if guard:
        return guard

    files = _list_weldb_files(directory)
    if not files:
        return f"No .weldb files in {directory} — skipped CSV generation."

    quarantine = _quarantine_dir(directory)

    point_rows: list[dict[str, Any]] = []
    linear_rows: list[dict[str, Any]] = []
    area_rows: list[dict[str, Any]] = []

    seen_points: dict[str, str] = {}  # prefixed_id -> source filename
    quarantined: list[str] = []

    for filepath in files:
        try:
            # Validate via the library loader (same rules as render/extract), so a
            # file that fails validation here also fails there — no drift.
            doc = load(filepath)
            panel_name = doc["panel_name"]

            maps = doc.get("maps", [])
            if not maps:
                continue
            views = maps[-1].get("views", [])

            # Effective properties per weld (panel baseline + overrides), used to
            # enrich every row below so the CSV carries panel properties and weld
            # overrides alongside each weld.
            props_by_id = resolve_weld_properties(doc)

            # -- Point welds (deduplicated across views) --
            file_points: dict[str, None] = {}
            for view in views:
                for row in view.get("grid", []):
                    for cell in row:
                        if cell.startswith("*"):
                            file_points.setdefault(cell, None)

            for cell in file_points:
                prefixed_id = prefix_weld_id(panel_name, cell)
                if prefixed_id in seen_points:
                    raise ValueError(
                        f"Duplicate weld '{prefixed_id}' in "
                        f"{filepath.name} and {seen_points[prefixed_id]}"
                    )
                seen_points[prefixed_id] = filepath.name
                point_rows.append({
                    "panel": panel_name,
                    "weld_id": prefixed_id,
                    "source": filepath.name,
                    **_weld_props(props_by_id, cell),
                })

            # -- Linear welds (unique IDs) --
            linear_ids: dict[str, None] = {}
            for view in views:
                for row in view.get("grid", []):
                    for cell in row:
                        if cell.startswith("_"):
                            linear_ids.setdefault(cell, None)

            for cell in linear_ids:
                linear_rows.append({
                    "panel": panel_name,
                    "weld_id": prefix_weld_id(panel_name, cell),
                    "source": filepath.name,
                    **_weld_props(props_by_id, cell),
                })

            # -- Area welds (unique IDs) --
            area_ids: dict[str, None] = {}
            for view in views:
                for row in view.get("grid", []):
                    for cell in row:
                        if cell.startswith("@"):
                            area_ids.setdefault(cell, None)

            for cell in area_ids:
                area_rows.append({
                    "panel": panel_name,
                    "weld_id": prefix_weld_id(panel_name, cell),
                    "source": filepath.name,
                    **_weld_props(props_by_id, cell),
                })

        except Exception as exc:
            quarantine.mkdir(exist_ok=True)
            dest = quarantine / filepath.name
            shutil.move(str(filepath), str(dest))
            quarantined.append(f"{filepath.name}: {exc}")

    good_files = len(files) - len(quarantined)

    # Write the three CSVs. Identity columns lead; the resolved panel properties
    # and weld overrides follow as property columns (grid row/col are not exported).
    point_csv = directory / "point_welds.csv"
    _write_weld_csv(point_csv, point_rows, ["panel", "weld_id", "source"])

    linear_csv = directory / "linear_welds.csv"
    _write_weld_csv(linear_csv, linear_rows, ["panel", "weld_id", "source"])

    area_csv = directory / "area_welds.csv"
    _write_weld_csv(area_csv, area_rows, ["panel", "weld_id", "source"])

    lines = [
        f"From {good_files} file(s) in {directory}:",
        f"  {point_csv.name}: {len(point_rows)} point welds",
        f"  {linear_csv.name}: {len(linear_rows)} linear welds",
        f"  {area_csv.name}: {len(area_rows)} area welds",
    ]
    if quarantined:
        lines.append(f"Quarantined {len(quarantined)} file(s):")
        for q in quarantined:
            lines.append(f"  {q}")
    return "\n".join(lines)


# Run CSV generation at import/startup time against the default project directory
# (the working directory the server was launched in) — NOT the examples catalog.
# When the working directory holds no panels this is a harmless no-op; agents drive
# the real work by passing project_path to regenerate_all_csv_files.
_startup_msg = _regenerate_all_csv_files(DEFAULT_PROJECT_DIR)
print(_startup_msg, file=sys.stderr)


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@mcp.tool()
def list_panels(project_path: str | None = None) -> str:
    """List all .weldb panel files in the user's project directory.

    Pass ``project_path`` pointing at the user's project folder (the directory
    holding their .weldb panels). Returns panel names, tube material, tube range,
    and revision info so the AI can understand the current project state. A file
    that cannot be loaded is listed with its error rather than aborting the whole
    listing.
    """
    directory = _find_project_dir(project_path)
    files = _list_weldb_files(directory)
    if not files:
        return f"No .weldb files found in {directory}"

    lines = [f"Project directory: {directory}", f"Panels ({len(files)}):", ""]
    for f in files:
        # Validate each file with the library loader; report per-file failures
        # instead of letting one malformed file break the entire listing.
        try:
            doc = load(f)
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
                f"  {doc.get('panel_name', f.stem):8s}  "
                f"mtrl={doc.get('tube_mtrl', '?')}  "
                f"od={doc.get('tube_od', '?')}  "
                f"wall={doc.get('tube_wall', '?')}  "
                f"units={doc.get('units', '?')}  "
                f"rev={latest.get('rev', '?')}  "
                f"welds={point_count}"
            )
        except Exception as exc:  # noqa: BLE001 — report, don't abort the listing
            lines.append(f"  {f.stem:8s}  <error: {exc}>")
    return "\n".join(lines)


@mcp.tool()
def read_panel(panel_name: str, project_path: str | None = None) -> str:
    """Read and return the full YAML content of a specific panel file.

    Pass ``project_path`` pointing at the user's project folder. Use this to
    inspect an existing panel's structure, grid layout, weld overrides, and
    revision history.
    """
    directory = _find_project_dir(project_path)
    filepath = _resolve_panel_path(directory, panel_name)
    if filepath is None:
        return f"Invalid panel name '{panel_name}'."
    if not filepath.exists():
        return f"Panel file not found: {filepath}"
    return filepath.read_text()


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
    project_path: str | None = None,
    custom_fields: dict[str, Any] | None = None,
) -> str:
    """Create a new .weldb panel file with hot_side and cold_side views.

    Before calling this tool, you MUST:
    1. Determine the correct panel_name using the panel naming convention
       (wall code + next sequential number). Use list_panels to see existing panels.
    2. Confirm tube_mtrl, tube_od, tube_wall, units, and elevation with the user.
    3. Know the tube range (tube_start and tube_end inclusive).

    The tool generates a standard layout with membrane welds between tubes,
    point welds at tube top/bottom, and an empty cold-side view.

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
        project_path: The user's project folder to write the panel into.
        custom_fields: Optional dict of extra top-level fields (e.g., client, job_number).

    Returns a confirmation message with the file path and weld count.
    """
    directory = _find_project_dir(project_path)

    # Validate panel name format
    m = _WALL_RE.match(panel_name)
    if not m:
        return (
            f"Invalid panel name '{panel_name}'. "
            f"Expected format: <wall_code><number> (e.g., N5, W3, LS2). "
            f"Valid wall codes: {', '.join(WALL_CODES)}"
        )

    if units not in VALID_UNITS:
        return f"Invalid units '{units}'. Must be one of: {', '.join(VALID_UNITS)}."

    if not elevation.strip():
        return "elevation is required and must not be empty (e.g. '1850 in' or 'Scaffold L3')."

    guard = _reject_code_dir(directory)
    if guard:
        return guard

    # Check for name collision
    filepath = _resolve_panel_path(directory, panel_name)
    if filepath is None:
        return f"Invalid panel name '{panel_name}'."
    if filepath.exists():
        return f"Panel '{panel_name}' already exists at {filepath}. Choose a different name."

    if tube_start > tube_end:
        return f"tube_start ({tube_start}) must be <= tube_end ({tube_end})."

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
            doc[k] = v

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

    directory.mkdir(parents=True, exist_ok=True)
    save(doc, filepath)

    # Validate the written file by loading it back (same rules as render/extract),
    # so create_panel never leaves an unloadable file behind.
    try:
        load(filepath)
    except Exception as exc:  # noqa: BLE001 — surface the failure and clean up
        filepath.unlink(missing_ok=True)
        return f"create_panel produced an invalid file and aborted (no file written): {exc}"

    num_tubes = tube_end - tube_start + 1
    point_welds = num_tubes * 2  # top + bottom per tube
    return (
        f"Created {filepath}\n"
        f"  Panel: {panel_name}\n"
        f"  Tubes: {tube_start}-{tube_end} ({num_tubes} tubes)\n"
        f"  Point welds: {point_welds}\n"
        f"  Membrane welds: {num_tubes + 1}\n"
        f"  Views: hot_side, cold_side"
    )


@mcp.tool()
def extract_weld_positions(
    panel_name: str,
    project_path: str | None = None,
    canvas_w: float | None = None,
    canvas_h: float | None = None,
    include_text: bool = False,
) -> str:
    """Locate every weld on the panel's rendered PDF, as a JSON coordinate map.

    Use this to find where each weld sits **on the PDF that render_pdf produces**
    — e.g. to drop a pin, highlight, or clickable hotspot onto that drawing. The
    coordinates describe the rendered PDF page, NOT the .weldb source; the typical
    workflow is render_pdf(panel) to produce the sheet, then this tool to get the
    weld boxes that line up with it.

    Note the ``panel_name`` argument is the panel's file stem (the same one you
    pass to render_pdf), e.g. ``N5`` — do NOT pass a ``.pdf`` (or ``.weldb``) file
    path or name. The tool reads the ``.weldb`` panel and derives the PDF geometry
    internally from the identical layout math render_pdf uses, so no PDF file has
    to exist first.

    Writes ``<panel_name>_weld_positions.json`` into the user's project folder
    (next to the panel) and returns its content. For each weld region the JSON
    holds a bounding box (upper-left ``x0,y0`` and lower-right ``x1,y1`` corners)
    in the rendered PDF's coordinate space: millimetres, origin at the
    **top-left** of the page, y increasing downward. The page width and height
    (also in mm) are included so a consumer can map the boxes onto any canvas.
    Coordinates match exactly where each weld is drawn by render_pdf — welds are
    reported per drawn region (an interrupted membrane run yields one entry per
    shape), and an empty back/cold view uses its mirrored layout, as drawn.

    QC Database pixel conversion: pass ``canvas_w`` and ``canvas_h`` (the target
    canvas size in pixels). Each weld then also gets integer ``px0, py0, px1,
    py1`` pixel corners, scaled proportionally from mm — ``px = x_mm /
    page_width * canvas_w`` and ``py = y_mm / page_height * canvas_h`` (no
    vertical flip, since both spaces put the origin at the top-left). Omit them
    to keep the file device-independent.

    Args:
        panel_name: Panel identifier — the file stem only (e.g. N5), not a
            filename or path and not a .pdf.
        project_path: The user's project folder holding the panel file; the JSON
            is written here too.
        canvas_w: Optional target canvas width in pixels (enables px output).
        canvas_h: Optional target canvas height in pixels (enables px output).
        include_text: If true, also report plain-text regions (tube numbers,
            annotations), not just welds. Empty regions are never reported.

    Returns the path written and the JSON content.
    """
    directory = _find_project_dir(project_path)
    guard = _reject_code_dir(directory)
    if guard:
        return guard
    filepath = _resolve_panel_path(directory, panel_name)
    if filepath is None:
        return f"Invalid panel name '{panel_name}'."
    if not filepath.exists():
        return f"Panel file not found: {filepath}"

    if (canvas_w is None) != (canvas_h is None):
        return "Provide both canvas_w and canvas_h for pixel output, or neither."
    if canvas_w is not None and (canvas_w <= 0 or canvas_h <= 0):
        return "canvas_w and canvas_h must be positive."

    try:
        from weldb import write_weld_positions
    except ImportError as exc:
        return f"Weld position extraction unavailable: {exc}"

    out_path = directory / f"{panel_name}_weld_positions.json"
    try:
        written = write_weld_positions(
            filepath,
            output_path=out_path,
            include_text=include_text,
            canvas_w=canvas_w,
            canvas_h=canvas_h,
        )
    except Exception as exc:  # noqa: BLE001 — surface the failure to the caller
        return f"Failed to extract weld positions from {filepath.name}: {exc}"

    return f"Wrote {written}\n\n{written.read_text(encoding='utf-8')}"


@mcp.tool()
def render_revision_history(panel_name: str, project_path: str | None = None) -> str:
    """Render a panel's full revision history to a standalone PDF.

    Writes ``<panel_name>_revisions.pdf`` into the user's project folder, listing
    every revision in a bordered table with the columns Rev, Date, Updated By,
    and Comments, ordered oldest to newest and paginated across as many sheets as
    needed. Unlike the abbreviated revision block on the main drawing (which is
    capped to what fits), this is the complete, unabridged history.

    Args:
        panel_name: Panel identifier (file stem, e.g. N5).
        project_path: The user's project folder holding the panel file; the PDF
            is written here too.

    Requires the optional fpdf2 dependency (pip install weldb[pdf]).
    """
    directory = _find_project_dir(project_path)
    guard = _reject_code_dir(directory)
    if guard:
        return guard
    filepath = _resolve_panel_path(directory, panel_name)
    if filepath is None:
        return f"Invalid panel name '{panel_name}'."
    if not filepath.exists():
        return f"Panel file not found: {filepath}"

    try:
        from weldb import render_revision_history_pdf
    except ImportError as exc:
        return f"PDF rendering unavailable: {exc}"

    out_path = directory / f"{panel_name}_revisions.pdf"
    try:
        written = render_revision_history_pdf(filepath, output_path=out_path)
        n_revs = len(load(filepath).get("maps", []))
    except Exception as exc:  # noqa: BLE001 — surface the failure to the caller
        return f"Failed to render revision history for {filepath.name}: {exc}"

    return f"Wrote {written} ({n_revs} revision(s))"


@mcp.tool()
def render_pdf(
    panel_name: str, project_path: str | None = None, color: bool = False
) -> str:
    """Render a project panel to a single-sheet vector engineering-drawing PDF.

    Writes ``<panel_name>.pdf`` into the user's project folder (next to the panel
    file) from the panel's latest revision. The sheet has a double-width border;
    the top 80% holds the views (drawn left to right, each grid scaled to fill its
    box, an empty back/cold view mirrored from its non-empty sibling); a
    double-width line separates the bottom 20% title block (properties, legend and
    weld tallies, and the most recent revisions that fit). This is the panel's own
    drawing — for the read-only bundled catalog use render_example instead.

    Args:
        panel_name: Panel identifier (file stem, e.g. N5).
        project_path: The user's project folder holding the panel file; the PDF
            is written here too.
        color: When true, grid cells are tinted with light, text-safe colors
            (grey for blank cells, pastel green/blue/orange for point/linear/area
            welds; plain-label cells stay white) and the legend gains matching
            swatches. The default renders black-on-white.

    Requires the optional fpdf2 dependency (pip install weldb[pdf]).
    """
    directory = _find_project_dir(project_path)
    guard = _reject_code_dir(directory)
    if guard:
        return guard
    filepath = _resolve_panel_path(directory, panel_name)
    if filepath is None:
        return f"Invalid panel name '{panel_name}'."
    if not filepath.exists():
        return f"Panel file not found: {filepath}"

    try:
        from weldb import render_pdf as _render_pdf
    except ImportError as exc:
        return f"PDF rendering unavailable: {exc}"

    out_path = directory / f"{panel_name}.pdf"
    try:
        written = _render_pdf(filepath, color=color, output_path=out_path)
    except Exception as exc:  # noqa: BLE001 — surface the failure to the caller
        return f"Failed to render {filepath.name}: {exc}"

    return f"Wrote {written} ({'color' if color else 'black-and-white'})"


@mcp.tool()
def suggest_panel_name(wall_code: str, project_path: str | None = None) -> str:
    """Suggest the next panel name for a given wall code.

    Use this after determining which wall the user is referring to.
    For example, if the user says 'west wall', pass wall_code='W'.

    Valid wall codes are the entries in WALL_CODES (single-letter walls N, S, E,
    W, T, F, H, D; features LS, US, TB, BN; corners NE, NW, SE, SW; and the
    directional disambiguations WLS, ELS, NTB, STB, NBN, SBN, ND, SD). The error
    message lists the full set if an unknown code is passed.
    """
    wall_code = wall_code.upper()
    if wall_code not in WALL_CODES:
        return f"Unknown wall code '{wall_code}'. Valid codes: {', '.join(WALL_CODES)}"
    directory = _find_project_dir(project_path)
    name = _next_panel_name(directory, wall_code)
    return f"Next available panel name for {wall_code} wall: {name}"


@mcp.tool()
def list_docs() -> str:
    """List all specification and documentation files (.md) in the project.

    Returns file names and first-line descriptions. Use read_doc to
    read the full content of any document.
    """
    md_files = sorted(SPEC_DIR.glob("*.md"))
    if not md_files:
        return "No documentation files found."

    lines = ["Available documentation:", ""]
    for f in md_files:
        first_line = ""
        with open(f) as fh:
            for line in fh:
                line = line.strip()
                if line.startswith("# "):
                    first_line = line[2:]
                    break
        lines.append(f"  {f.name:40s} {first_line}")
    return "\n".join(lines)


@mcp.tool()
def read_doc(filename: str) -> str:
    """Read the full content of a specification or documentation file.

    Pass the filename (e.g., 'drawing_spec.md', 'philosophy.md',
    'panel_naming_convention.md'). Only .md files in the project root
    are accessible.
    """
    if not filename.endswith(".md"):
        return "Only .md files can be read with this tool."

    filepath = SPEC_DIR / filename
    if not filepath.exists():
        return f"File not found: {filename}. Use list_docs to see available files."

    # Prevent path traversal
    if not filepath.resolve().parent == SPEC_DIR.resolve():
        return "Access denied."

    return filepath.read_text()


# ---------------------------------------------------------------------------
# Example catalog — reference .weldb files organized by panel arrangement
# ---------------------------------------------------------------------------


@mcp.tool()
def list_examples() -> str:
    """List the example arrangements in the examples/ catalog.

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
    return filepath.read_text()


@mcp.tool()
def render_example(
    example: str, filename: str | None = None, project_path: str | None = None
) -> str:
    """Render example .weldb file(s) to PDF in the user's project folder.

    The examples catalog is a read-only reference, so the generated PDFs are
    written into ``project_path`` (the user's project folder) — never back into
    the examples directory. Pass an example folder name and optionally a single
    .weldb file name; if filename is omitted, every .weldb file in the folder is
    rendered. Each PDF keeps the source stem with a .pdf extension.
    Requires the optional fpdf2 dependency (pip install weldb[pdf]).
    """
    folder = _resolve_example_path(example)
    if folder is None or not folder.is_dir():
        names = ", ".join(d.name for d in _list_example_dirs()) or "(none)"
        return f"Example '{example}' not found. Available: {names}"

    if filename is not None:
        target = _resolve_example_path(example, filename)
        if target is None or not target.is_file():
            return f"File '{filename}' not found in example '{example}'."
        targets = [target]
    else:
        targets = _list_weldb_files(folder)
        if not targets:
            return f"Example '{example}' has no .weldb files to render."

    out_dir = _find_project_dir(project_path)
    guard = _reject_code_dir(out_dir)
    if guard:
        return guard

    try:
        from weldb import render_pdf
    except ImportError as exc:
        return f"PDF rendering unavailable: {exc}"

    out_dir.mkdir(parents=True, exist_ok=True)
    rendered: list[str] = []
    errors: list[str] = []
    for src in targets:
        try:
            pdf_path = render_pdf(src, output_path=out_dir / f"{src.stem}.pdf")
            rendered.append(pdf_path.name)
        except Exception as exc:  # noqa: BLE001 — report per-file failures
            errors.append(f"{src.name}: {exc}")

    lines = [f"Rendered {len(rendered)} PDF(s) from examples/{example}/ into {out_dir}:"]
    lines += [f"  {p}" for p in rendered]
    if errors:
        lines.append(f"Failed ({len(errors)}):")
        lines += [f"  {e}" for e in errors]
    return "\n".join(lines)


@mcp.tool()
def quarantine_panel(panel_name: str, project_path: str | None = None) -> str:
    """Move a problematic panel file to the quarantine/ subdirectory.

    Use this when a panel file causes exceptions during loading or
    weld extraction, or when the user identifies a file as malformed.
    The file is preserved for investigation but excluded from the
    active weld log and CSV export.
    """
    directory = _find_project_dir(project_path)
    guard = _reject_code_dir(directory)
    if guard:
        return guard
    filepath = _resolve_panel_path(directory, panel_name)
    if filepath is None:
        return f"Invalid panel name '{panel_name}'."
    if not filepath.exists():
        return f"Panel file not found: {filepath}"

    quarantine = _quarantine_dir(directory)
    quarantine.mkdir(exist_ok=True)
    dest = quarantine / filepath.name
    if dest.exists():
        return f"'{panel_name}.weldb' is already in quarantine."
    shutil.move(str(filepath), str(dest))
    return f"Moved {filepath.name} to {quarantine}/"


@mcp.tool()
def restore_from_quarantine(panel_name: str, project_path: str | None = None) -> str:
    """Restore a panel file from quarantine/ back to the project directory.

    Use this after fixing the issue that caused the file to be quarantined.
    """
    directory = _find_project_dir(project_path)
    guard = _reject_code_dir(directory)
    if guard:
        return guard
    quarantine = _quarantine_dir(directory)
    src = _resolve_panel_path(quarantine, panel_name)
    dest = _resolve_panel_path(directory, panel_name)
    if src is None or dest is None:
        return f"Invalid panel name '{panel_name}'."
    if not src.exists():
        return f"'{panel_name}.weldb' not found in quarantine."
    if dest.exists():
        return f"'{panel_name}.weldb' already exists in the project directory. Remove or rename it first."
    shutil.move(str(src), str(dest))
    return f"Restored {panel_name}.weldb to {directory}/"


@mcp.tool()
def archive_panel(panel_name: str, project_path: str | None = None) -> str:
    """Move a panel file to the archive/ subdirectory.

    Use this for cancelled scope, superseded designs, or completed teardowns.
    The file is preserved for audit but excluded from the active weld log.
    Never delete panel files — archive them instead.
    """
    directory = _find_project_dir(project_path)
    guard = _reject_code_dir(directory)
    if guard:
        return guard
    filepath = _resolve_panel_path(directory, panel_name)
    if filepath is None:
        return f"Invalid panel name '{panel_name}'."
    if not filepath.exists():
        return f"Panel file not found: {filepath}"

    archive = _archive_dir(directory)
    archive.mkdir(exist_ok=True)
    dest = archive / filepath.name
    if dest.exists():
        return f"'{panel_name}.weldb' is already in archive."
    shutil.move(str(filepath), str(dest))
    return f"Archived {filepath.name} to {archive}/"


@mcp.tool()
def restore_from_archive(panel_name: str, project_path: str | None = None) -> str:
    """Restore a panel file from archive/ back to the project directory.

    Use this when cancelled scope is reinstated.
    """
    directory = _find_project_dir(project_path)
    guard = _reject_code_dir(directory)
    if guard:
        return guard
    archive = _archive_dir(directory)
    src = _resolve_panel_path(archive, panel_name)
    dest = _resolve_panel_path(directory, panel_name)
    if src is None or dest is None:
        return f"Invalid panel name '{panel_name}'."
    if not src.exists():
        return f"'{panel_name}.weldb' not found in archive."
    if dest.exists():
        return f"'{panel_name}.weldb' already exists in the project directory. Remove or rename it first."
    shutil.move(str(src), str(dest))
    return f"Restored {panel_name}.weldb to {directory}/"


@mcp.tool()
def list_quarantine(project_path: str | None = None) -> str:
    """List all files in the quarantine/ subdirectory."""
    directory = _find_project_dir(project_path)
    quarantine = _quarantine_dir(directory)
    if not quarantine.exists():
        return "No quarantine directory exists (no files have been quarantined)."
    files = sorted(quarantine.glob("*.weldb"))
    if not files:
        return "Quarantine is empty."
    lines = [f"Quarantined files ({len(files)}):"]
    for f in files:
        lines.append(f"  {f.name}")
    return "\n".join(lines)


@mcp.tool()
def list_archive(project_path: str | None = None) -> str:
    """List all files in the archive/ subdirectory."""
    directory = _find_project_dir(project_path)
    archive = _archive_dir(directory)
    if not archive.exists():
        return "No archive directory exists (no files have been archived)."
    files = sorted(archive.glob("*.weldb"))
    if not files:
        return "Archive is empty."
    lines = [f"Archived files ({len(files)}):"]
    for f in files:
        lines.append(f"  {f.name}")
    return "\n".join(lines)


@mcp.tool()
def regenerate_all_csv_files(project_path: str | None = None) -> str:
    """Regenerate all three CSV files from active .weldb files.

    Pass ``project_path`` pointing at the user's project folder. Produces
    point_welds.csv, linear_welds.csv, and area_welds.csv in that folder. Each
    weld row carries its effective properties — the panel's top-level properties
    (material, OD, wall, units, elevation, custom fields) merged with the
    type-level and weld-specific overrides that apply (e.g. linear length, area
    height). Call this after creating, archiving, quarantining, or restoring
    panels to keep the CSVs up to date. (A startup pass also runs against the
    server's working directory, which is a no-op unless panels happen to live
    there.)
    """
    directory = _find_project_dir(project_path)
    return _regenerate_all_csv_files(directory)


# ---------------------------------------------------------------------------
# Prompts — guide the AI's conversational behavior
# ---------------------------------------------------------------------------


@mcp.prompt()
def create_panel_workflow() -> str:
    """Guided workflow for creating a new boiler panel from user description."""
    return (
        "The user wants to create a new boiler panel weld map. Follow these steps:\n\n"
        "1. First, call list_panels to see what panels already exist in the project.\n"
        "2. Call read_doc with 'panel_naming_convention.md' to understand naming rules.\n"
        "3. From the user's description, determine:\n"
        "   - Which wall (N, S, E, W, T, LS, H, TB, etc.)\n"
        "   - The tube range (e.g., tubes 125 to 150)\n"
        "4. Call suggest_panel_name with the wall code to get the next available name.\n"
        "5. Ask the user for tube parameters if not already provided:\n"
        "   - tube_mtrl (e.g., SA-210 A1)\n"
        "   - tube_od (e.g., 2.0)\n"
        "   - tube_wall (e.g., 0.15)\n"
        "   - units (e.g., in)\n"
        "   - elevation (e.g., 1850 in, or Scaffold L3)\n"
        "6. Confirm all parameters with the user before calling create_panel.\n"
        "7. After creation, show the user what was created."
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run(transport="stdio")
