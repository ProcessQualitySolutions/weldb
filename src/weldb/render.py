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
_VIEW_GAP = 0.0              # gap around/between view boxes (0 = boxes touch border & each other)
_VIEW_PAD = 2.5              # white space between the view box edge and its name
_GRID_PAD = 7.5             # white space around the grid graphic (3x _VIEW_PAD)
_MIN_COL_CHARS = 2           # minimum content-width weight for a grid column
_PT_TO_MM = 0.352778

# Grid-cell label fit: fraction of the cell usable by the (bold) label along the
# reading direction and across it. Higher = tighter padding, larger text. Applied
# to both horizontal and vertical labels.
_LABEL_READ_FRAC = 0.94      # along the text reading direction (cell width if horizontal)
_LABEL_CROSS_FRAC = 0.84     # across the text (cell height if horizontal)

# Optional light cell fills (see ``render_pdf(color=True)``). All are pale
# enough that black text stays readable on top of them.
_FILL_EMPTY = (236, 236, 236)   # light grey  — blank / whitespace cells
_FILL_POINT = (208, 240, 210)   # pastel green — point welds (*)
_FILL_LINEAR = (206, 224, 246)  # pastel blue  — linear welds (_)
_FILL_AREA = (250, 228, 200)    # pastel orange — area welds (@)


def _region_fill(label: str) -> tuple[int, int, int] | None:
    """Light background fill for a merged region, or ``None`` to leave it white.

    Empty/whitespace regions get light grey; point (``*``), linear (``_``) and
    area (``@``) welds get pastel green/blue/orange respectively. A region with
    a non-weld label (e.g. a tube number or note) stays white.
    """
    if not label:
        return _FILL_EMPTY
    if label.startswith("*"):
        return _FILL_POINT
    if label.startswith("_"):
        return _FILL_LINEAR
    if label.startswith("@"):
        return _FILL_AREA
    return None

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


def _text_centered_vertical(pdf, x: float, y: float, w: float, h: float, text: str, size: float, style: str = "") -> None:
    """Draw text centered in a box but rotated 90° (reads bottom-to-top)."""
    pdf.set_font("Helvetica", style, size)
    cx, cy = x + w / 2, y + h / 2
    safe = _latin1(text)
    tw = pdf.get_string_width(safe)
    line_h = size * _PT_TO_MM
    with pdf.rotation(90, cx, cy):
        # Lay the text out horizontally on the pivot; the rotation makes it vertical.
        pdf.set_xy(cx - tw / 2, cy - line_h / 2)
        pdf.cell(tw, line_h, safe, align="C")


def _truncate(pdf, text: str, max_w: float) -> str:
    """Truncate ``text`` (with a trailing ellipsis) to fit ``max_w`` mm at the current font."""
    text = _latin1(text)
    if pdf.get_string_width(text) <= max_w:
        return text
    ell = "..."
    while text and pdf.get_string_width(text + ell) > max_w:
        text = text[:-1]
    return (text + ell) if text else ""


def _wrap_text(pdf, text: str, max_w: float) -> list[str]:
    """Word-wrap ``text`` into lines that each fit ``max_w`` mm at the current font.

    A single word too long to fit on its own is left on its own (overflowing)
    line rather than being broken mid-word. Returns ``[""]`` for empty input.
    """
    words = _latin1(text).split()
    if not words:
        return [""]
    lines: list[str] = []
    cur = ""
    for word in words:
        trial = f"{cur} {word}".strip()
        if not cur or pdf.get_string_width(trial) <= max_w:
            cur = trial
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def _cell_value(cell: str) -> str:
    """Normalised cell value used for merge comparisons (whitespace ignored)."""
    return cell.strip()


def _merged_neighbors(grid: Grid, r1: int, c1: int, r2: int, c2: int) -> bool:
    """True if two cells hold the same label (incl. both empty) and should merge."""
    return _cell_value(grid[r1][c1]) == _cell_value(grid[r2][c2])


def _cell_regions(grid: Grid) -> list[tuple[str, list[tuple[int, int]]]]:
    """Group edge-adjacent cells with the identical value into connected regions.

    Uses 4-connectivity over *all* cells — welds, plain text, tube numbers, and
    empty cells alike: adjacent cells sharing the same value merge into one
    region, so the borders between them are dropped on render. A cell with a
    different value — e.g. a point weld breaking a run, or any neighbouring
    label — interrupts adjacency, so an interrupted run like ``_A _A *T5 _A _A``
    yields two separate ``_A`` regions, each keeping its own label.

    Returns one ``(label, cells)`` per region, where ``cells`` is the list of
    the region's member ``(row, col)`` coordinates and ``label`` is the shared
    (stripped) value (empty for blank regions). Callers must work from the
    member cells, not a bounding box: a region can be L-shaped (e.g. an antler
    tube number) or even disjoint-looking after a single empty cell bridges two
    columns, so a bounding box would spill onto cells owned by other regions.
    """
    rows = len(grid)
    cols = len(grid[0]) if grid else 0
    seen: set[tuple[int, int]] = set()
    regions: list[tuple[str, list[tuple[int, int]]]] = []
    for r in range(rows):
        for c in range(cols):
            if (r, c) in seen:
                continue
            label = _cell_value(grid[r][c])
            stack = [(r, c)]
            seen.add((r, c))
            cells: list[tuple[int, int]] = []
            while stack:
                cr, cc = stack.pop()
                cells.append((cr, cc))
                for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    nr, nc = cr + dr, cc + dc
                    if (
                        0 <= nr < rows
                        and 0 <= nc < cols
                        and (nr, nc) not in seen
                        and _cell_value(grid[nr][nc]) == label
                    ):
                        seen.add((nr, nc))
                        stack.append((nr, nc))
            regions.append((label, cells))
    return regions


def _anchor_cell(cells: list[tuple[int, int]]) -> tuple[int, int]:
    """Pick the member cell to carry a merged region's label.

    Returns the cell nearest the region's centroid (ties broken top-left), so
    the single label sits where one of the real cells is — centred within that
    one cell, never floated across the whole (possibly L-shaped) region where it
    could land outside the drawn cell boundaries.
    """
    cr = sum(r for r, _ in cells) / len(cells)
    cc = sum(c for _, c in cells) / len(cells)
    return min(cells, key=lambda rc: ((rc[0] - cr) ** 2 + (rc[1] - cc) ** 2, rc[0], rc[1]))


def _column_edges(grid: Grid, ax: float, aw: float) -> list[float]:
    """X positions of the ``cols + 1`` vertical column edges, scaled to content.

    Each column's width is proportional to the longest label it contains (in
    characters), so columns holding longer strings (e.g. ``*T250``) get more
    room than narrow ones (e.g. ``_A``). Every column gets at least
    ``_MIN_COL_CHARS`` of weight so empty/narrow columns stay visible.
    """
    rows = len(grid)
    cols = len(grid[0]) if grid else 0
    weights: list[float] = []
    for c in range(cols):
        longest = max((len(grid[r][c].strip()) for r in range(rows)), default=0)
        weights.append(float(max(longest, _MIN_COL_CHARS)))
    total = sum(weights) or 1.0
    edges = [ax]
    for w in weights:
        edges.append(edges[-1] + aw * w / total)
    edges[-1] = ax + aw  # guard against float drift
    return edges


def _draw_grid_vector(
    pdf, grid: Grid, ax: float, ay: float, aw: float, ah: float, color: bool = False
) -> None:
    """Draw a weld-map grid as vector lines, scaled to fill (not outgrow) the area.

    Adjacent cells with the identical value are visually merged (see
    render_spec.md): the borders between them are dropped so the group reads as
    one shape, and the label is drawn once per merged region. Merging applies to
    every label — welds, plain text, tube numbers, and empty cells — and works
    in any direction; a differing cell (e.g. a point weld) interrupts a run into
    independently-labelled regions. Column widths scale to their content.

    When ``color`` is true, each merged region is filled with a light tint keyed
    to its content (grey for blanks; pastel green/blue/orange for point/linear/
    area welds; white for plain labels) so the map reads at a glance while black
    text stays legible.

    For wide grids (more than 30 columns and more than twice as many columns as
    rows, per render_spec.md), labels are rendered rotated 90° (vertical) so the
    text can take a larger font than the narrow column width would allow.
    """
    rows = len(grid)
    cols = max((len(r) for r in grid), default=0)
    if rows == 0 or cols == 0 or aw <= 0 or ah <= 0:
        return

    vertical = cols > 30 and cols > 2 * rows

    colx = _column_edges(grid, ax, aw)
    rowh = ah / rows

    regions = _cell_regions(grid)

    # Light fills first (so grid lines and labels sit on top). Fill each region's
    # actual member cells — never a bounding box, which would bleed a region's
    # colour onto cells owned by other regions (e.g. an empty region graying a
    # tube number it merely straddles).
    if color:
        for label, cells in regions:
            fill = _region_fill(label)
            if fill is None:
                continue
            pdf.set_fill_color(*fill)
            for r, c in cells:
                pdf.rect(colx[c], ay + r * rowh, colx[c + 1] - colx[c], rowh, style="F")

    # One label per merged region, centred in a single member cell (its anchor)
    # so it stays within that cell's drawn boundaries.
    labels: list[tuple[str, float, float, float, float]] = []  # text, x, y, w, h
    for label, cells in regions:
        if not label:
            continue
        ar, ac = _anchor_cell(cells)
        labels.append((label, colx[ac], ay + ar * rowh, colx[ac + 1] - colx[ac], rowh))

    # One uniform font size: the largest that fits every (bold) label in its box.
    # When labels are vertical the text runs along the cell height and its line
    # height is bounded by the cell width, so the fit extents are swapped.
    font_size = 11.0
    for text, _lx, _ly, lw, lh in labels:
        if vertical:
            read, cross = lh, lw
        else:
            read, cross = lw, lh
        font_size = min(
            font_size,
            _fit_font_size(pdf, text, read * _LABEL_READ_FRAC, cross * _LABEL_CROSS_FRAC, style="B"),
        )

    # Cell borders: draw each cell's left and top edge unless it is shared with a
    # merged same-value neighbour; two outer lines close off the right and bottom.
    pdf.set_draw_color(0, 0, 0)
    pdf.set_line_width(_LW_THIN)
    for r in range(rows):
        y = ay + r * rowh
        for c in range(cols):
            x = colx[c]
            if c == 0 or not _merged_neighbors(grid, r, c, r, c - 1):
                pdf.line(x, y, x, y + rowh)
            if r == 0 or not _merged_neighbors(grid, r, c, r - 1, c):
                pdf.line(x, y, colx[c + 1], y)
    pdf.line(ax + aw, ay, ax + aw, ay + ah)
    pdf.line(ax, ay + ah, ax + aw, ay + ah)

    # Labels last (bold), so text sits on top of the grid lines.
    for text, lx, ly, lw, lh in labels:
        if vertical:
            _text_centered_vertical(pdf, lx, ly, lw, lh, text, font_size, style="B")
        else:
            _text_centered(pdf, lx, ly, lw, lh, text, font_size, style="B")


def _view_label(name: str) -> str:
    """Upper-cased view-box title with " VIEW" appended.

    Underscores become spaces and the result is upper-cased (e.g. ``hot_side``
    -> ``HOT SIDE VIEW``). The word "VIEW" is only appended when it is not
    already present as a whole word, so a name like ``cold side view`` stays
    ``COLD SIDE VIEW`` rather than gaining a second "VIEW".
    """
    label = name.replace("_", " ").upper()
    if "VIEW" in label.split():
        return label
    return f"{label} VIEW"


def _draw_view(
    pdf, view: dict[str, Any], x: float, y: float, w: float, h: float, color: bool = False
) -> None:
    """Draw a single view: single-line border, name in the upper-left, scaled grid."""
    pdf.set_draw_color(0, 0, 0)
    pdf.set_line_width(_LW_VIEW)
    pdf.rect(x, y, w, h)

    name = _view_label(view["name"])
    name_size = _fit_font_size(pdf, name, w - 2 * _VIEW_PAD, 4.5, style="B", start=9.0)
    name_h = name_size * _PT_TO_MM
    pdf.set_font("Helvetica", "B", name_size)
    pdf.set_xy(x + _VIEW_PAD, y + _VIEW_PAD)
    pdf.cell(w - 2 * _VIEW_PAD, name_h, _latin1(name))

    grid = view["grid"]
    cols = max((len(r) for r in grid), default=0)

    gx = x + _GRID_PAD
    gy = y + _VIEW_PAD + name_h + _GRID_PAD
    gw = w - 2 * _GRID_PAD
    gh = (y + h - _GRID_PAD) - gy
    # Square rule: cap the rendered width at its height so a wide (e.g.
    # single-view) box does not stretch the map; center the narrower graphic in
    # the available width. Ignored for very wide grids (>40 cols), which need the
    # full width to stay legible (see render_spec.md).
    if gw > gh and cols <= 40:
        gx += (gw - gh) / 2
        gw = gh
    _draw_grid_vector(pdf, grid, gx, gy, gw, gh, color=color)


def _field_label(key: str) -> str:
    """Format a top-level field key as a drawing label (``panel_length`` -> ``Panel Length``)."""
    return key.replace("_", " ").title()


def _draw_title_block(
    pdf, doc: dict[str, Any], x: float, y: float, w: float, h: float, color: bool = False
) -> None:
    """Draw the bottom title block: properties | legend & notes | revisions.

    When ``color`` is true the legend's weld lines are prefixed with a small
    filled swatch in their pastel tint (matching the colored grid cells); the
    grey/white cell colors are left unlabeled as self-explanatory.
    """
    pad = 3.0
    bx, by, bw, bh = x + pad, y + pad, w - 2 * pad, h - 2 * pad

    props_w = bw * 0.25
    mid_w = bw * 0.25
    rev_w = bw * 0.50
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
    elev = str(doc.get("elevation", "")).strip()
    elev_at = str(doc.get("elevation_at", "")).strip()
    if elev:
        prop_lines.append(f"Elevation: {elev}" + (f" ({elev_at})" if elev_at else ""))
    custom_keys = [k for k in doc if k not in RESERVED_FIELDS]
    prop_lines += [f"{_field_label(k)}: {doc[k]}" for k in custom_keys]

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
        ("* point weld", _FILL_POINT),
        ("_ linear weld", _FILL_LINEAR),
        ("@ area weld", _FILL_AREA),
    ]
    sw = 2.6  # swatch side (mm); only drawn when color is on
    pdf.set_font("Helvetica", "", 7.5)
    for line, fill in legend:
        if color:
            pdf.set_fill_color(*fill)
            pdf.set_draw_color(0, 0, 0)
            pdf.set_line_width(_LW_THIN)
            pdf.rect(mid_x + 2, cy + (3.3 - sw) / 2, sw, sw, style="DF")
            tx = mid_x + 2 + sw + 1.2
        else:
            tx = mid_x + 2
        pdf.set_xy(tx, cy)
        pdf.cell(mid_w - 3 - (tx - (mid_x + 2)), 3.3, _truncate(pdf, line, mid_w - 3 - (tx - (mid_x + 2))))
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

    # Newest first; each comment wraps onto as many lines as it needs (never
    # truncated). Stop once a row would overflow the block, but always draw the
    # newest revision even if it is the only one that fits.
    line_h = 3.4
    row_gap = 0.6
    bottom = by + bh
    ry = hy + 4.0
    pdf.set_font("Helvetica", "", 7)
    for m in reversed(doc.get("maps", [])):
        comment_lines = _wrap_text(pdf, str(m.get("comments", "")), desc_w)
        row_h = len(comment_lines) * line_h + row_gap
        if ry > hy + 4.0 and ry + row_h > bottom:
            break
        pdf.set_xy(rcx, ry)
        pdf.cell(rev_col, line_h, _latin1(str(m.get("rev", ""))))
        pdf.set_xy(rcx + rev_col, ry)
        pdf.cell(date_col, line_h, _latin1(str(m.get("date", ""))))
        ly = ry
        for cline in comment_lines:
            pdf.set_xy(desc_x, ly)
            pdf.cell(desc_w, line_h, cline)
            ly += line_h
        ry += row_h


def _is_empty_grid(grid: Grid) -> bool:
    """True if every cell of a grid is blank."""
    return all(not cell.strip() for row in grid for cell in row)


def _mirror_non_area(grid: Grid) -> Grid:
    """Mirror a grid for the opposite face.

    The back/cold face is seen from behind, so each row is **reversed
    left-to-right** — tube 250 on the left of the hot side sits on the right of
    the cold side. It shows the same point welds, membrane (linear) welds, tube
    numbers and annotations, but not surface area welds (e.g. cladding), which
    are one-sided.
    """
    return [
        ["" if cell.strip().startswith("@") else cell for cell in reversed(row)]
        for row in grid
    ]


def _display_views(doc: dict[str, Any]) -> list[dict[str, Any]]:
    """Views to draw on the sheet.

    A view whose grid is empty is rendered by mirroring the first non-empty
    sibling (columns reversed left-to-right, since the back is seen from behind;
    point/linear welds, plain text and tube numbers carried over; area welds
    dropped) — an empty back view is pointless otherwise. An empty view with no
    sibling to mirror from is omitted entirely. Views with their own content are
    drawn as-is. This is display-only; weld tallies still come from the stored
    grids, so welds are never double-counted.
    """
    views = _current_views(doc)
    nonempty = [v for v in views if not _is_empty_grid(v["grid"])]
    result: list[dict[str, Any]] = []
    for v in views:
        if _is_empty_grid(v["grid"]):
            src = next((s for s in nonempty if s is not v), None)
            if src is None:
                continue
            result.append({"name": v["name"], "grid": _mirror_non_area(src["grid"])})
        else:
            result.append(v)
    return result


def render_pdf(source_path: str | Path, color: bool = False) -> Path:
    """Render a .weldb file to a single-sheet vector PDF in the same directory.

    The PDF has the same stem as the source file with a .pdf extension and is
    laid out as an engineering drawing (see render_spec.md):

    - The whole sheet has a double-width border.
    - The top 80% holds the views, drawn left to right with equal width, each in
      its own single-line box with the view name in the upper left. Each grid
      scales to fill (without outgrowing) its box, with column widths scaled to
      their content. An empty (e.g. back/cold) view is mirrored from its
      non-empty sibling — reversed left-to-right with area welds dropped — or
      omitted if there is nothing to mirror.
    - A double-width line separates the views from the bottom 20%, which is the
      title block: drawing properties, legend/tallies/NOT TO SCALE, and the most
      recent revisions that fit.

    Everything is scaled to fit on one sheet. Returns the path to the PDF.

    When ``color`` is true, grid cells are tinted with light, text-safe colors:
    light grey for blank cells, pastel green for point welds, pastel blue for
    linear welds and pastel orange for area welds; cells with a non-weld label
    stay white. The default (``False``) renders black-on-white.

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
    views = _display_views(doc)
    n = len(views)
    if n > 0:
        g = _VIEW_GAP
        view_w = (iw - g * (n + 1)) / n
        view_h = views_h - 2 * g
        for i, view in enumerate(views):
            vx = m + g + i * (view_w + g)
            vy = m + g
            _draw_view(pdf, view, vx, vy, view_w, view_h, color=color)

    # --- Title block (bottom 20%) ---
    _draw_title_block(pdf, doc, m, title_y, iw, title_h, color=color)

    pdf.output(str(pdf_path))
    return pdf_path
