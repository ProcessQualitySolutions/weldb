"""Rendering of weldb documents (monospace and PDF)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from weldb.document import FILE_EXTENSION, RESERVED_FIELDS
from weldb.welds import Grid, _current_views, resolve_weld_properties


def _linear_weld_length_tally(doc: dict[str, Any]) -> tuple[bool, float]:
    """Check if all linear welds have length and return the total.

    Returns (all_have_length, total_length).
    """
    props = resolve_weld_properties(doc)
    linear_props = {k: v for k, v in props.items() if k.startswith("_")}
    if not linear_props:
        return False, 0.0
    total = 0.0
    for wid, p in linear_props.items():
        length = p.get("length")
        if length is None:
            return False, 0.0
        total += float(length)
    return True, total


def _area_weld_tally(doc: dict[str, Any]) -> tuple[bool, float]:
    """Check if all area welds have length and height, return total area.

    Returns (all_have_dims, total_area).
    """
    props = resolve_weld_properties(doc)
    area_props = {k: v for k, v in props.items() if k.startswith("@")}
    if not area_props:
        return False, 0.0
    total = 0.0
    for wid, p in area_props.items():
        length = p.get("length")
        height = p.get("height")
        if length is None or height is None:
            return False, 0.0
        total += int(length) * int(height)
    return True, total


def _render_grid(grid: Grid, col_width: int = 8) -> str:
    """Render a single grid as a monospace text table."""
    if not grid or not grid[0]:
        return ""

    rows = len(grid)
    cols = len(grid[0])

    # Build spanning weld cell map (linear and area welds merge in rows)
    linear_cell_map: dict[tuple[int, int], str] = {}
    for r in range(rows):
        for c in range(cols):
            cell = grid[r][c]
            if cell.startswith("_") or cell.startswith("@"):
                linear_cell_map[(r, c)] = cell

    # Determine span starts
    span_start: dict[tuple[int, int], int] = {}
    skip: set[tuple[int, int]] = set()

    for r in range(rows):
        c = 0
        while c < cols:
            wid = linear_cell_map.get((r, c))
            if wid is not None:
                span_len = 1
                while c + span_len < cols and linear_cell_map.get((r, c + span_len)) == wid:
                    span_len += 1
                span_start[(r, c)] = span_len
                for offset in range(1, span_len):
                    skip.add((r, c + offset))
                c += span_len
            else:
                c += 1

    lines: list[str] = []

    for r in range(rows):
        # Top border row
        border_parts = ["+"]
        c = 0
        while c < cols:
            if (r, c) in span_start:
                span_len = span_start[(r, c)]
                merged_width = col_width * span_len + (span_len - 1)
                border_parts.append("-" * merged_width + "+")
                c += span_len
            else:
                border_parts.append("-" * col_width + "+")
                c += 1
        lines.append("".join(border_parts))

        # Content row
        content_parts = ["|"]
        c = 0
        while c < cols:
            cell = grid[r][c]

            if (r, c) in span_start:
                span_len = span_start[(r, c)]
                merged_width = col_width * span_len + (span_len - 1)
                content_parts.append(cell.center(merged_width) + "|")
                c += span_len
            elif (r, c) in skip:
                c += 1
            elif cell.startswith("*"):
                content_parts.append(cell.center(col_width) + "|")
                c += 1
            else:
                content_parts.append(cell.center(col_width) + "|")
                c += 1

        lines.append("".join(content_parts))

    # Bottom border
    c = 0
    border_parts = ["+"]
    while c < cols:
        if (rows - 1, c) in span_start:
            span_len = span_start[(rows - 1, c)]
            merged_width = col_width * span_len + (span_len - 1)
            border_parts.append("-" * merged_width + "+")
            c += span_len
        else:
            border_parts.append("-" * col_width + "+")
            c += 1
    lines.append("".join(border_parts))

    return "\n".join(lines)


def render_monospace(doc: dict[str, Any], col_width: int = 8) -> str:
    """Render the current (latest) map of a weldb document as monospace text.

    Always operates on the last map in the maps array.

    Each view is rendered as a separate grid with a label above it.
    Views are separated by a blank line.

    Rules (per render_spec.md):
    - Point welds (* prefix): rendered as-is with bordered cell.
    - Linear welds (_ prefix): rendered as-is. Cells sharing the same linear
      weld ID in the same row are visually merged (single label, no internal
      borders).
    - Plain text: rendered as-is.
    - Empty cells: blank.
    """
    views = _current_views(doc)
    sections: list[str] = []

    for view in views:
        view_name = view["name"].replace("_", " ").upper()
        grid_text = _render_grid(view["grid"], col_width)
        if grid_text:
            sections.append(f"[ {view_name} ]\n{grid_text}")

    all_have_length, total = _linear_weld_length_tally(doc)
    if all_have_length:
        units = doc.get("units", "")
        sections.append(f"Total linear weld length: {total:g} {units}")
    else:
        sections.append("Linear weld length not recorded")

    all_have_dims, total_area = _area_weld_tally(doc)
    if all_have_dims:
        units = doc.get("units", "")
        sections.append(f"Total area weld: {total_area:g} {units}^2")
    elif any(k.startswith("@") for v in _current_views(doc) for row in v["grid"] for k in row):
        sections.append("Area weld dimensions not recorded")

    return "\n\n".join(sections)


def render_pdf(source_path: str | Path) -> Path:
    """Render a .weldb file to a minimalistic PDF in the same directory.

    The PDF has the same stem as the source file with a .pdf extension.
    Returns the path to the written PDF.

    Requires the ``fpdf2`` package (install with ``pip install weldb[pdf]``).
    """
    try:
        from fpdf import FPDF
    except ImportError as exc:
        raise ImportError(
            "PDF rendering requires fpdf2. Install with: pip install weldb[pdf]"
        ) from exc

    from weldb.document import load

    source_path = Path(source_path)
    doc = load(source_path)
    pdf_path = source_path.with_suffix(".pdf")

    pdf = FPDF(orientation="L", unit="mm", format="letter")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    # --- Header: required fields + custom fields ---
    pdf.set_font("Courier", "B", 14)
    pdf.cell(0, 8, doc.get("panel_name", ""), new_x="LMARGIN", new_y="NEXT")

    pdf.set_font("Courier", "", 9)
    meta_parts = [
        f"Material: {doc.get('tube_mtrl', '')}",
        f"OD: {doc.get('tube_od', '')}",
        f"Wall: {doc.get('tube_wall', '')}",
        f"Units: {doc.get('units', '')}",
    ]
    pdf.cell(0, 5, "  |  ".join(meta_parts), new_x="LMARGIN", new_y="NEXT")

    # Custom fields
    custom_keys = [k for k in doc if k not in RESERVED_FIELDS]
    if custom_keys:
        custom_parts = [f"{k}: {doc[k]}" for k in custom_keys]
        pdf.cell(0, 5, "  |  ".join(custom_parts), new_x="LMARGIN", new_y="NEXT")

    pdf.ln(4)

    # --- View grids (monospace) ---
    views = _current_views(doc)
    pdf.set_font("Courier", "", 7)
    line_height = 3.2

    for view in views:
        view_label = view["name"].replace("_", " ").upper()
        grid_text = _render_grid(view["grid"])

        pdf.set_font("Courier", "B", 9)
        pdf.cell(0, 5, view_label, new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Courier", "", 7)

        for line in grid_text.split("\n"):
            if pdf.get_y() > pdf.h - 20:
                pdf.add_page()
            pdf.cell(0, line_height, line, new_x="LMARGIN", new_y="NEXT")
        pdf.ln(3)

    # --- Revision history table ---
    maps = doc.get("maps", [])
    recent = maps[-10:]  # last 10 revisions

    if recent:
        if pdf.get_y() > pdf.h - 40:
            pdf.add_page()

        pdf.set_font("Courier", "B", 9)
        pdf.cell(0, 5, "REVISION HISTORY", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(1)

        col_widths = [18, 28, 30, 0]  # Rev, Date, Updated By, Comments (fill)
        comments_w = pdf.w - pdf.l_margin - pdf.r_margin - sum(col_widths[:3])
        col_widths[3] = comments_w
        headers = ["Rev", "Date", "Updated By", "Comments"]

        pdf.set_font("Courier", "B", 7)
        for i, hdr in enumerate(headers):
            pdf.cell(col_widths[i], 4, hdr, border=1)
        pdf.ln()

        pdf.set_font("Courier", "", 7)
        for m in recent:
            for i, key in enumerate(["rev", "date", "updated_by", "comments"]):
                pdf.cell(col_widths[i], 4, str(m.get(key, "")), border=1)
            pdf.ln()

    # --- Linear weld length tally ---
    pdf.ln(4)
    if pdf.get_y() > pdf.h - 20:
        pdf.add_page()
    all_have_length, total = _linear_weld_length_tally(doc)
    pdf.set_font("Courier", "", 8)
    if all_have_length:
        units = doc.get("units", "")
        pdf.cell(0, 4, f"Total linear weld length: {total:g} {units}", new_x="LMARGIN", new_y="NEXT")
    else:
        pdf.cell(0, 4, "Linear weld length not recorded", new_x="LMARGIN", new_y="NEXT")

    # --- Area weld tally ---
    all_have_dims, total_area = _area_weld_tally(doc)
    has_area_welds = any(
        k.startswith("@") for v in views for row in v["grid"] for k in row
    )
    if all_have_dims:
        units = doc.get("units", "")
        pdf.cell(0, 4, f"Total area weld: {total_area:g} {units}^2", new_x="LMARGIN", new_y="NEXT")
    elif has_area_welds:
        pdf.cell(0, 4, "Area weld dimensions not recorded", new_x="LMARGIN", new_y="NEXT")

    # --- Legend ---
    pdf.ln(4)
    if pdf.get_y() > pdf.h - 20:
        pdf.add_page()
    pdf.set_font("Courier", "B", 9)
    pdf.cell(0, 5, "LEGEND", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Courier", "", 8)
    pdf.cell(0, 4, "* = Point weld (discrete weld at a single location)", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 4, "_ = Linear weld (continuous weld spanning multiple cells)", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 4, "@ = Area weld (surface weld spanning multiple cells, e.g. cladding)", new_x="LMARGIN", new_y="NEXT")

    # --- Not to scale notice ---
    pdf.ln(3)
    pdf.set_font("Courier", "B", 8)
    pdf.cell(0, 4, "NOT TO SCALE", new_x="LMARGIN", new_y="NEXT")

    pdf.output(str(pdf_path))
    return pdf_path
