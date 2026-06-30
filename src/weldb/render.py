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


def _compute_spans(
    grid: Grid,
) -> tuple[dict[tuple[int, int], int], set[tuple[int, int]]]:
    """Compute horizontal merge spans for linear/area welds.

    Consecutive cells in the same row sharing the same linear (``_``) or area
    (``@``) weld ID are merged into a single span.

    Returns ``(span_start, skip)`` where ``span_start[(r, c)]`` is the span
    length of the span that begins at ``(r, c)``, and ``skip`` is the set of
    cells absorbed into a span to their left.
    """
    rows = len(grid)
    cols = len(grid[0]) if grid else 0

    linear_cell_map: dict[tuple[int, int], str] = {}
    for r in range(rows):
        for c in range(cols):
            cell = grid[r][c]
            if cell.startswith("_") or cell.startswith("@"):
                linear_cell_map[(r, c)] = cell

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

    return span_start, skip


def _render_grid(grid: Grid, col_width: int = 8) -> str:
    """Render a single grid as a monospace text table."""
    if not grid or not grid[0]:
        return ""

    rows = len(grid)
    cols = len(grid[0])

    span_start, skip = _compute_spans(grid)

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


# ---------------------------------------------------------------------------
# PDF rendering — single-sheet vector engineering drawing
# ---------------------------------------------------------------------------

# Sheet layout constants (mm) and line weights.
_SHEET_MARGIN = 7.0          # page edge -> outer (double) border
_LW_THIN = 0.2               # grid lines, column dividers
_LW_VIEW = 0.4               # single-line view border
_LW_DOUBLE = 0.8             # outer border + views/title separator
_VIEWS_FRACTION = 0.80       # top 80% for views, bottom 20% for title block
_VIEW_GAP = 5.0              # gap around/between view boxes
_VIEW_PAD = 2.5              # white space inside a view box (req: no touching)
_PT_TO_MM = 0.352778

_LATIN1_FALLBACK = {"—": "-", "–": "-", "“": '"', "”": '"', "’": "'", "²": "^2"}


def _latin1(text: str) -> str:
    """Make a string safe for the core PDF fonts (latin-1)."""
    for bad, good in _LATIN1_FALLBACK.items():
        text = text.replace(bad, good)
    return text.encode("latin-1", "replace").decode("latin-1")


def _fit_font_size(
    pdf, text: str, max_w: float, max_h: float, style: str = "",
    start: float = 11.0, minimum: float = 1.5,
) -> float:
    """Largest Helvetica size (pt) at which ``text`` fits in ``max_w`` x ``max_h`` mm."""
    size = start
    while size > minimum:
        pdf.set_font("Helvetica", style, size)
        if pdf.get_string_width(text) <= max_w and size * _PT_TO_MM <= max_h:
            return size
        size -= 0.5
    return minimum


def _text_centered(pdf, x: float, y: float, w: float, h: float, text: str, size: float, style: str = "") -> None:
    pdf.set_font("Helvetica", style, size)
    line_h = size * _PT_TO_MM
    pdf.set_xy(x, y + (h - line_h) / 2)
    pdf.cell(w, line_h, _latin1(text), align="C")


def _truncate(pdf, text: str, max_w: float) -> str:
    """Truncate ``text`` (with a trailing ellipsis) to fit ``max_w`` mm at the current font."""
    text = _latin1(text)
    if pdf.get_string_width(text) <= max_w:
        return text
    ell = "..."
    while text and pdf.get_string_width(text + ell) > max_w:
        text = text[:-1]
    return (text + ell) if text else ""


def _draw_grid_vector(pdf, grid: Grid, ax: float, ay: float, aw: float, ah: float) -> None:
    """Draw a weld-map grid as vector lines, scaled to fill (not outgrow) the area.

    Cells are square and uniformly sized; the grid is centered in the area.
    Linear/area weld runs are merged into a single bordered span.
    """
    rows = len(grid)
    cols = len(grid[0]) if grid else 0
    if rows == 0 or cols == 0 or aw <= 0 or ah <= 0:
        return

    span_start, _ = _compute_spans(grid)

    # Fill the whole area (cells need not be square — the grid is schematic).
    cellw = aw / cols
    cellh = ah / rows

    # One uniform font size for all labels: the largest that fits every label
    # in its own cell (spans get extra width and so are never the constraint).
    font_size = 11.0
    for r in range(rows):
        c = 0
        while c < cols:
            span = span_start.get((r, c), 1)
            label = grid[r][c].strip()
            if label:
                avail_w = cellw * span * 0.88
                avail_h = cellh * 0.66
                font_size = min(font_size, _fit_font_size(pdf, label, avail_w, avail_h))
            c += span

    pdf.set_draw_color(0, 0, 0)
    pdf.set_line_width(_LW_THIN)

    for r in range(rows):
        c = 0
        while c < cols:
            span = span_start.get((r, c), 1)
            w = cellw * span
            x = ax + c * cellw
            y = ay + r * cellh
            pdf.rect(x, y, w, cellh)
            label = grid[r][c].strip()
            if label:
                _text_centered(pdf, x, y, w, cellh, label, font_size)
            c += span


def _draw_view(pdf, view: dict[str, Any], x: float, y: float, w: float, h: float) -> None:
    """Draw a single view: single-line border, name in the upper-left, scaled grid."""
    pdf.set_draw_color(0, 0, 0)
    pdf.set_line_width(_LW_VIEW)
    pdf.rect(x, y, w, h)

    name = view["name"].replace("_", " ").upper()
    name_size = _fit_font_size(pdf, name, w - 2 * _VIEW_PAD, 4.5, style="B", start=9.0)
    name_h = name_size * _PT_TO_MM
    pdf.set_font("Helvetica", "B", name_size)
    pdf.set_xy(x + _VIEW_PAD, y + _VIEW_PAD)
    pdf.cell(w - 2 * _VIEW_PAD, name_h, _latin1(name))

    gx = x + _VIEW_PAD
    gy = y + _VIEW_PAD + name_h + 1.5
    gw = w - 2 * _VIEW_PAD
    gh = h - 2 * _VIEW_PAD - name_h - 1.5
    _draw_grid_vector(pdf, view["grid"], gx, gy, gw, gh)


def _draw_title_block(pdf, doc: dict[str, Any], x: float, y: float, w: float, h: float) -> None:
    """Draw the bottom title block: properties | legend & notes | revisions."""
    pad = 3.0
    bx, by, bw, bh = x + pad, y + pad, w - 2 * pad, h - 2 * pad

    props_w = bw * 0.30
    mid_w = bw * 0.28
    rev_w = bw * 0.42
    props_x = bx
    mid_x = bx + props_w
    rev_x = bx + props_w + mid_w

    # Column dividers
    pdf.set_draw_color(0, 0, 0)
    pdf.set_line_width(_LW_THIN)
    pdf.line(mid_x, y + 1, mid_x, y + h - 1)
    pdf.line(rev_x, y + 1, rev_x, y + h - 1)

    # --- Properties column ---
    cy = by
    panel = str(doc.get("panel_name", ""))
    psize = _fit_font_size(pdf, panel, props_w - 2, 7.0, style="B", start=18.0)
    pdf.set_font("Helvetica", "B", psize)
    pdf.set_xy(props_x, cy)
    pdf.cell(props_w - 2, psize * _PT_TO_MM, _latin1(panel))
    cy += psize * _PT_TO_MM + 2.0

    prop_lines = [
        f"Material: {doc.get('tube_mtrl', '')}",
        f"Tube OD: {doc.get('tube_od', '')}   Wall: {doc.get('tube_wall', '')}",
        f"Units: {doc.get('units', '')}",
    ]
    custom_keys = [k for k in doc if k not in RESERVED_FIELDS]
    prop_lines += [f"{k}: {doc[k]}" for k in custom_keys]

    pdf.set_font("Helvetica", "", 8)
    for line in prop_lines:
        if cy > by + bh:
            break
        pdf.set_xy(props_x, cy)
        pdf.cell(props_w - 2, 3.6, _truncate(pdf, line, props_w - 3))
        cy += 3.9

    # --- Middle column: legend, tallies, NOT TO SCALE ---
    cy = by
    pdf.set_font("Helvetica", "B", 8)
    pdf.set_xy(mid_x + 2, cy)
    pdf.cell(mid_w - 3, 3.6, "LEGEND")
    cy += 4.0
    legend = [
        "* point weld",
        "_ linear weld",
        "@ area weld",
    ]
    pdf.set_font("Helvetica", "", 7.5)
    for line in legend:
        pdf.set_xy(mid_x + 2, cy)
        pdf.cell(mid_w - 3, 3.3, _truncate(pdf, line, mid_w - 3))
        cy += 3.5

    cy += 1.0
    all_len, total_len = _linear_weld_length_tally(doc)
    units = doc.get("units", "")
    lin_text = (
        f"Linear total: {total_len:g} {units}" if all_len else "Linear length not recorded"
    )
    pdf.set_xy(mid_x + 2, cy)
    pdf.cell(mid_w - 3, 3.3, _truncate(pdf, lin_text, mid_w - 3))
    cy += 3.5

    all_dims, total_area = _area_weld_tally(doc)
    has_area = any(k.startswith("@") for v in _current_views(doc) for row in v["grid"] for k in row)
    if has_area:
        area_text = (
            f"Area total: {total_area:g} {units}^2" if all_dims else "Area dims not recorded"
        )
        pdf.set_xy(mid_x + 2, cy)
        pdf.cell(mid_w - 3, 3.3, _truncate(pdf, area_text, mid_w - 3))
        cy += 3.5

    pdf.set_font("Helvetica", "B", 9)
    pdf.set_xy(mid_x + 2, by + bh - 4.0)
    pdf.cell(mid_w - 3, 3.6, "NOT TO SCALE")

    # --- Revisions column: last N that fit, newest first ---
    rcx = rev_x + 2
    rcw = rev_w - 3
    pdf.set_font("Helvetica", "B", 8)
    pdf.set_xy(rcx, by)
    pdf.cell(rcw, 3.6, "REVISIONS")
    header_h = 4.2
    row_h = 4.0

    rev_col = 11.0
    date_col = 22.0
    desc_x = rcx + rev_col + date_col
    desc_w = rcw - rev_col - date_col

    # Column headers
    pdf.set_font("Helvetica", "B", 6.5)
    hy = by + header_h
    pdf.set_xy(rcx, hy)
    pdf.cell(rev_col, 3.2, "REV")
    pdf.set_xy(rcx + rev_col, hy)
    pdf.cell(date_col, 3.2, "DATE")
    pdf.set_xy(desc_x, hy)
    pdf.cell(desc_w, 3.2, "DESCRIPTION")
    pdf.set_line_width(_LW_THIN)
    pdf.line(rcx, hy + 3.4, rcx + rcw, hy + 3.4)

    avail = (by + bh) - (hy + 3.6)
    n_fit = max(0, int(avail / row_h))
    maps = doc.get("maps", [])
    recent = list(reversed(maps[-n_fit:])) if n_fit else []

    ry = hy + 4.0
    pdf.set_font("Helvetica", "", 7)
    for m in recent:
        pdf.set_xy(rcx, ry)
        pdf.cell(rev_col, 3.4, _latin1(str(m.get("rev", ""))))
        pdf.set_xy(rcx + rev_col, ry)
        pdf.cell(date_col, 3.4, _latin1(str(m.get("date", ""))))
        pdf.set_xy(desc_x, ry)
        pdf.cell(desc_w, 3.4, _truncate(pdf, str(m.get("comments", "")), desc_w))
        ry += row_h


def render_pdf(source_path: str | Path) -> Path:
    """Render a .weldb file to a single-sheet vector PDF in the same directory.

    The PDF has the same stem as the source file with a .pdf extension and is
    laid out as an engineering drawing (see render_spec.md):

    - The whole sheet has a double-width border.
    - The top 80% holds the views, drawn left to right with equal width and
      spacing, each in its own single-line box with the view name in the upper
      left. Each grid scales to fill (without outgrowing) its box.
    - A double-width line separates the views from the bottom 20%, which is the
      title block: drawing properties, legend/tallies/NOT TO SCALE, and the most
      recent revisions that fit.

    Everything is scaled to fit on one sheet. Returns the path to the PDF.

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
    pdf.set_auto_page_break(auto=False)
    pdf.set_margins(0, 0, 0)
    pdf.add_page()

    pw, ph = pdf.w, pdf.h
    m = _SHEET_MARGIN
    iw = pw - 2 * m
    ih = ph - 2 * m

    # Outer double-width border.
    pdf.set_draw_color(0, 0, 0)
    pdf.set_line_width(_LW_DOUBLE)
    pdf.rect(m, m, iw, ih)

    views_h = ih * _VIEWS_FRACTION
    title_y = m + views_h
    title_h = ih - views_h

    # Double-width separator between views and title block.
    pdf.set_line_width(_LW_DOUBLE)
    pdf.line(m, title_y, m + iw, title_y)

    # --- Views region (top 80%) ---
    views = _current_views(doc)
    n = len(views)
    if n > 0:
        g = _VIEW_GAP
        view_w = (iw - g * (n + 1)) / n
        view_h = views_h - 2 * g
        for i, view in enumerate(views):
            vx = m + g + i * (view_w + g)
            vy = m + g
            _draw_view(pdf, view, vx, vy, view_w, view_h)

    # --- Title block (bottom 20%) ---
    _draw_title_block(pdf, doc, m, title_y, iw, title_h)

    pdf.output(str(pdf_path))
    return pdf_path
