"""weldb MCP Server — AI-assisted weld map management.

Provides tools for creating and inspecting boiler weld map panels,
listing existing project files, and reading specification documents.

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

import yaml
from mcp.server.fastmcp import FastMCP

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

PROJECT_DIR = Path.cwd()
SPEC_DIR = PROJECT_DIR  # md files live at repo root
EXAMPLES_DIR = PROJECT_DIR / "examples"

mcp = FastMCP(
    "weldb",
    instructions=(
        "You are a weld map database assistant. You help users create and manage "
        "boiler panel weld maps (.weldb files). When the user asks to create a "
        "panel, gather the required information through conversation before calling "
        "create_panel. Required: panel_name, tube_mtrl, tube_od, tube_wall, units, "
        "tube_start, tube_end. Use the panel_naming_convention and existing panels "
        "to determine the correct panel name. Always confirm parameters with the "
        "user before creating."
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


def _find_project_dir(path: str | None) -> Path:
    """Resolve the project directory from an optional path argument."""
    if path:
        p = Path(path)
        return p if p.is_dir() else p.parent
    return EXAMPLES_DIR


def _quarantine_dir(directory: Path) -> Path:
    return directory / "quarantine"


def _archive_dir(directory: Path) -> Path:
    return directory / "archive"


def _list_weldb_files(directory: Path) -> list[Path]:
    """List .weldb files in directory root (excludes quarantine/ and archive/)."""
    return sorted(directory.glob("*.weldb"))


def _next_panel_name(directory: Path, wall: str) -> str:
    """Determine the next sequential panel name for a given wall code."""
    existing_nums: list[int] = []
    for f in _list_weldb_files(directory):
        m = _WALL_RE.match(f.stem)
        if m and m.group(1) == wall:
            existing_nums.append(int(m.group(2)))
    next_num = max(existing_nums, default=0) + 1
    return f"{wall}{next_num}"


def _build_grid(tube_start: int, tube_end: int) -> list[list[str]]:
    """Build a basic hot-side grid for a tube range.

    Layout: membrane columns between each tube, with outer membranes on
    both edges. Top row has top welds, bottom row has bottom welds,
    middle rows are empty.
    """
    tubes = list(range(tube_start, tube_end + 1))
    num_tubes = len(tubes)
    # Membrane labels: _A, _B, _C, ...
    num_membranes = num_tubes + 1
    membrane_labels = [f"_{chr(65 + i)}" for i in range(num_membranes)]

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
            top_row.append(f"*{tubes[tube_idx]}T")
            bottom_row.append(f"*{tubes[tube_idx]}B")
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

WELD_PREFIXES_MAP = {"*": "point", "_": "linear", "@": "area"}


def _regenerate_all_csv_files(directory: Path) -> str:
    """Load all .weldb files, extract all weld types, write three CSV files.

    Generates:
      - point_welds.csv  — one row per point weld (deduplicated across views)
      - linear_welds.csv — one row per linear weld ID (with cell count)
      - area_welds.csv   — one row per area weld ID (with cell count)

    Files that raise exceptions are moved to quarantine/.
    Returns a status message.
    """
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
            doc = yaml.safe_load(filepath.read_text())
            panel_name = doc["panel_name"]

            maps = doc.get("maps", [])
            if not maps:
                continue
            views = maps[-1].get("views", [])

            # -- Point welds (deduplicated across views) --
            file_points: dict[str, tuple[int, int]] = {}
            for view in views:
                for r, row in enumerate(view.get("grid", [])):
                    for c, cell in enumerate(row):
                        if cell.startswith("*") and cell not in file_points:
                            file_points[cell] = (r, c)

            for cell, (r, c) in file_points.items():
                label = cell[1:]
                prefixed_id = f"{panel_name}-{label}"
                if prefixed_id in seen_points:
                    raise ValueError(
                        f"Duplicate weld '{prefixed_id}' in "
                        f"{filepath.name} and {seen_points[prefixed_id]}"
                    )
                seen_points[prefixed_id] = filepath.name
                point_rows.append({
                    "panel": panel_name,
                    "weld_id": prefixed_id,
                    "row": r,
                    "col": c,
                    "source": filepath.name,
                })

            # -- Linear welds (unique IDs, cell count) --
            linear_groups: dict[str, int] = {}
            for view in views:
                for row in view.get("grid", []):
                    for cell in row:
                        if cell.startswith("_"):
                            linear_groups[cell] = linear_groups.get(cell, 0) + 1

            for cell, count in linear_groups.items():
                linear_rows.append({
                    "panel": panel_name,
                    "weld_id": f"{panel_name}-{cell[1:]}",
                    "cells": count,
                    "source": filepath.name,
                })

            # -- Area welds (unique IDs, cell count) --
            area_groups: dict[str, int] = {}
            for view in views:
                for row in view.get("grid", []):
                    for cell in row:
                        if cell.startswith("@"):
                            area_groups[cell] = area_groups.get(cell, 0) + 1

            for cell, count in area_groups.items():
                area_rows.append({
                    "panel": panel_name,
                    "weld_id": f"{panel_name}-{cell[1:]}",
                    "cells": count,
                    "source": filepath.name,
                })

        except Exception as exc:
            quarantine.mkdir(exist_ok=True)
            dest = quarantine / filepath.name
            shutil.move(str(filepath), str(dest))
            quarantined.append(f"{filepath.name}: {exc}")

    good_files = len(files) - len(quarantined)

    # Write point_welds.csv
    point_csv = directory / "point_welds.csv"
    with open(point_csv, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["panel", "weld_id", "row", "col", "source"])
        writer.writeheader()
        writer.writerows(point_rows)

    # Write linear_welds.csv
    linear_csv = directory / "linear_welds.csv"
    with open(linear_csv, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["panel", "weld_id", "cells", "source"])
        writer.writeheader()
        writer.writerows(linear_rows)

    # Write area_welds.csv
    area_csv = directory / "area_welds.csv"
    with open(area_csv, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["panel", "weld_id", "cells", "source"])
        writer.writeheader()
        writer.writerows(area_rows)

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


# Run CSV generation at import/startup time
_startup_msg = _regenerate_all_csv_files(EXAMPLES_DIR)
print(_startup_msg, file=sys.stderr)


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@mcp.tool()
def list_panels(project_path: str | None = None) -> str:
    """List all .weldb panel files in the project directory.

    Returns panel names, tube material, tube range, and revision info
    so the AI can understand the current project state.
    """
    directory = _find_project_dir(project_path)
    files = _list_weldb_files(directory)
    if not files:
        return f"No .weldb files found in {directory}"

    lines = [f"Project directory: {directory}", f"Panels ({len(files)}):", ""]
    for f in files:
        with open(f) as fh:
            doc = yaml.safe_load(fh)
        maps = doc.get("maps", [])
        latest = maps[-1] if maps else {}
        views = latest.get("views", [])
        # Count welds in hot side
        point_count = 0
        for v in views:
            for row in v.get("grid", []):
                for cell in row:
                    if cell.startswith("*"):
                        point_count += 1
        lines.append(
            f"  {doc['panel_name']:8s}  "
            f"mtrl={doc.get('tube_mtrl', '?')}  "
            f"od={doc.get('tube_od', '?')}  "
            f"wall={doc.get('tube_wall', '?')}  "
            f"units={doc.get('units', '?')}  "
            f"rev={latest.get('rev', '?')}  "
            f"welds={point_count}"
        )
    return "\n".join(lines)


@mcp.tool()
def read_panel(panel_name: str, project_path: str | None = None) -> str:
    """Read and return the full YAML content of a specific panel file.

    Use this to inspect an existing panel's structure, grid layout,
    weld overrides, and revision history.
    """
    directory = _find_project_dir(project_path)
    filepath = directory / f"{panel_name}.weldb"
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
    tube_start: int,
    tube_end: int,
    updated_by: str = "mcp",
    comments: str = "Initial weld map layout",
    project_path: str | None = None,
    custom_fields: dict[str, Any] | None = None,
) -> str:
    """Create a new .weldb panel file with hot_side and cold_side views.

    Before calling this tool, you MUST:
    1. Determine the correct panel_name using the panel naming convention
       (wall code + next sequential number). Use list_panels to see existing panels.
    2. Confirm tube_mtrl, tube_od, tube_wall, and units with the user.
    3. Know the tube range (tube_start and tube_end inclusive).

    The tool generates a standard layout with membrane welds between tubes,
    point welds at tube top/bottom, and an empty cold-side view.

    Args:
        panel_name: Panel identifier (e.g., W3, N5, LS2). Must match wall code + number.
        tube_mtrl: Tube material spec (e.g., SA-210 A1).
        tube_od: Tube outside diameter.
        tube_wall: Tube wall thickness.
        units: One of: mm, ft_in, in, dec_in, dec_ft.
        tube_start: First tube number (inclusive).
        tube_end: Last tube number (inclusive).
        updated_by: Author of the revision.
        comments: Revision comment.
        project_path: Directory to write to. Defaults to examples/.
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

    # Check for name collision
    filepath = directory / f"{panel_name}.weldb"
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
    }

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
    with open(filepath, "w") as f:
        yaml.dump(doc, f, default_flow_style=False, sort_keys=False)

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
def suggest_panel_name(wall_code: str, project_path: str | None = None) -> str:
    """Suggest the next panel name for a given wall code.

    Use this after determining which wall the user is referring to.
    For example, if the user says 'west wall', pass wall_code='W'.

    Valid wall codes: N, S, E, W, T, F, LS, US, H, TB, NE, NW, SE, SW, D, B
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

    Pass the filename (e.g., 'drawing_spec_boiler.md', 'philosophy.md',
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


@mcp.tool()
def quarantine_panel(panel_name: str, project_path: str | None = None) -> str:
    """Move a problematic panel file to the quarantine/ subdirectory.

    Use this when a panel file causes exceptions during loading or
    weld extraction, or when the user identifies a file as malformed.
    The file is preserved for investigation but excluded from the
    active weld log and CSV export.
    """
    directory = _find_project_dir(project_path)
    filepath = directory / f"{panel_name}.weldb"
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
    quarantine = _quarantine_dir(directory)
    src = quarantine / f"{panel_name}.weldb"
    if not src.exists():
        return f"'{panel_name}.weldb' not found in quarantine."
    dest = directory / f"{panel_name}.weldb"
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
    filepath = directory / f"{panel_name}.weldb"
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
    archive = _archive_dir(directory)
    src = archive / f"{panel_name}.weldb"
    if not src.exists():
        return f"'{panel_name}.weldb' not found in archive."
    dest = directory / f"{panel_name}.weldb"
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

    Produces point_welds.csv, linear_welds.csv, and area_welds.csv.
    Call this after creating, archiving, quarantining, or restoring panels
    to ensure the CSVs are up to date. Also run automatically at server startup.
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
        "6. Confirm all parameters with the user before calling create_panel.\n"
        "7. After creation, show the user what was created."
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run(transport="stdio")
