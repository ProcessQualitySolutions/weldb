# Render Specification — Boiler (.weldb)

This document defines how weldb weld maps must be rendered visually, whether on the web, in a terminal, or in print. Implementations must follow these rules to ensure consistent, unambiguous weld map drawings.

## Prefix Characters

Only two weld prefix characters exist. No other prefix characters are permitted in the drawing.

| Weld Type    | Prefix | Description |
|-------------|--------|-------------|
| Point weld  | `*`    | Discrete weld at a single location. |
| Linear weld | `_`    | Segment of a continuous weld spanning multiple cells. |
| Area weld   | `@`    | Surface weld spanning multiple cells (e.g., cladding). |

The prefix characters (`*`, `_`, and `@`) are part of the weld label and **are rendered as-is** in the output. No substitution or icon replacement is performed.

Non-weld text cells (tube labels, annotations, etc.) are rendered as plain text with no prefix.

## Multi-View Rendering

Each map may contain multiple views (e.g., `hot_side`, `cold_side`). Each view must be rendered as a separate grid with its own label.

### View Label

Above each grid, render a **view label** showing the view name in a readable format. For example, a view named `hot_side` should display as `HOT SIDE` or `Hot Side`. The label must be visually distinct from the grid content (e.g., bold, uppercase, or underlined in monospace).

### View Order

Views are rendered in the order they appear in the `views` array. Each view's grid is rendered independently using the same cell rendering rules below.

### Spacing

A blank line or visual separator must appear between consecutive view grids to clearly distinguish them.

### Empty / Back Views

A view whose grid is entirely empty is **not** drawn as a blank box. Instead:

- If another view in the same map has content, the empty view is rendered by
  **mirroring** that sibling. Because the back is seen from behind, the mirror is
  **reversed left-to-right** — a tube on the left of the front view appears on
  the right of the back view. It shows the sibling's point welds, linear
  (membrane) welds, plain-text annotations and tube numbers, but **drops area
  welds** (`@`, e.g. cladding), which are usually one-sided. This gives a useful
  back/cold view without re-entering the welds.
- If there is no sibling to mirror from, the empty view is **omitted** entirely.

Mirroring is **display-only**: weld tallies and the weld record come from the
stored grids, so a mirrored weld is never double-counted.

This empty/back-view mirroring applies to the **PDF** renderer only. The
monospace renderer intentionally renders each view's stored grid as-is (an empty
grid is skipped, not mirrored), since terminal output is a quick text dump rather
than a drawing. The two renderers therefore differ on empty back views by
design.

## Cell Rendering Rules

### Point Welds

- A point weld cell has a **visible border on all four sides** (no two point
  welds are ever adjacent with the same ID within a view, so they never merge).
- Display the cell value as-is (e.g., `*W1`).

### Linear Welds

- Cells that share the same linear weld ID and are **visually adjacent** must be **visually merged** into a single shape (see [Merging Adjacent Cells](#merging-adjacent-cells)).
- The merged shape has **exterior borders only** — no internal cell borders within the shape.
- The weld label appears **at least once** within the merged shape, not repeated per cell.
- Display the cell value as-is (e.g., `_L1`).
- Linear weld cells that are **not adjacent** (e.g., separated by a point weld) form separate visual shapes, each labeled independently.

### Area Welds

- Rendered identically to linear welds in the grid: adjacent cells with the same area weld ID are **visually merged** (see [Merging Adjacent Cells](#merging-adjacent-cells)).
- Display the cell value as-is (e.g., `@CL1`).

### Merging Adjacent Cells

Any cells that hold the **identical value** and are **visually adjacent** are
merged: the borders between the merged cells are removed so the group reads as a
single shape, and a non-empty label is drawn **at least once** per group (it is
removed from the other cells, but never from all of them). This applies to
**every** label — point welds, linear (`_`) and area (`@`) welds, plain-text
annotations, tube numbers, **and empty strings** (adjacent blank cells merge
into one borderless blank region, so the grid interior is open space rather than
a lattice of empty boxes).

- **Adjacency is edge-sharing.** In the PDF renderer cells merge in **any
  direction** — horizontally across a row and vertically down a column — so a
  membrane bar (or a tube number repeated down a tube) renders as one continuous
  shape rather than a stack of separate boxes.
- **A differing cell interrupts a run.** A point weld — or any cell with a
  different value — breaks adjacency. The segments on either side form separate
  groups, and **each segment keeps its own label**; the label is never lost on
  one side of the interruption. For example, a row `[_A][_A][*T5][_A][_A]`
  renders as `[_A    ][*T5][_A    ]`.

This merging is a property of **rendering only**; it does not alter the stored
grid (the markup). The monospace/terminal renderer merges within a row only (a
limitation of a character grid); the PDF renderer merges in every direction.

### Column Widths

In the PDF renderer, grid **column widths scale to their content**: each
column's width is proportional to the longest label it contains, so a column of
tube welds (e.g. `*T250`) is wider than a narrow membrane column (e.g. `_A`).
Every column keeps a small minimum width so empty columns stay visible. Row
heights remain uniform.

### View Aspect Cap (Square Rule)

By default, a view's rendered grid is **capped so its drawn width never exceeds
its drawn height**, and is centered horizontally within its box. This keeps a
wide box — e.g. a single-view drawing that spans the full sheet — from
stretching a short map into distortion.

**Exception — wide grids.** When a grid has **more than 40 columns**, the square
rule is **ignored** and the grid expands to fill the full available width. At
that column count the per-column width is the limiting factor for legibility, so
the map must use all the horizontal room available.

### Vertical Labels (Wide Grids)

When a grid has **more than 30 columns** *and* its column count is **more than
twice its row count**, cell labels are rendered **rotated 90° (vertical, reading
bottom-to-top)**. Such grids have tall, narrow cells; orienting the label along
the cell's height lets it use a **larger font** than the narrow column width
would allow horizontally. All other grids render labels horizontally.

### Plain Text Cells

- No prefix, no special borders beyond the default grid lines.
- Rendered as-is. Tube numbers are plain-text cells placed on the tube columns
  (they carry no weld prefix), and merge like any other label.

### Empty Cells

- Rendered as blank space within the grid. Adjacent empty cells merge, so the
  interior reads as open space (see [Merging Adjacent Cells](#merging-adjacent-cells)).

## Color

Drawings **must not rely on color coding** to convey information. Color may be used as a supplementary visual aid (e.g., highlighting), but all information must be legible in monochrome.

## Linear Weld Length Tally

If **every** linear weld in the document has a resolved `length` value (via `weld_overrides`), the drawing must include a **linear weld length tally** showing the total length of all linear welds. The tally should appear near the legend or revision history.

If **any** linear weld is missing a `length` value, the tally must not be shown. Instead, render the text: **"Linear weld length not recorded"**.

This is all-or-nothing: either every linear weld has a length and the tally is displayed, or none is shown and the notice is displayed instead.

## Area Weld Area Tally

If **every** area weld in the document has resolved `length` and `height` values (both integers, via `weld_overrides`), the drawing must include an **area weld tally** showing the total area (sum of `length * height` for each area weld). The tally should appear near the linear weld tally.

If **any** area weld is missing `length` or `height`, the tally must not be shown. Instead, render the text: **"Area weld dimensions not recorded"**.

If the document contains no area welds, neither the tally nor the notice is shown.

## Legend

All rendered drawings **must include a legend** explaining the prefix characters. The legend must appear in the margins or footer of the drawing and contain at minimum:

- `*` = Point weld (discrete weld at a single location)
- `_` = Linear weld (continuous weld spanning multiple cells)
- `@` = Area weld (surface weld spanning multiple cells, e.g. cladding)

The legend must be present on every rendered page or sheet that contains a weld map grid.

## Not to Scale

All rendered drawings **must include a "NOT TO SCALE" notice**. This must appear prominently — either in the title bar / header area, or in the margin of the drawing. The grid is a schematic representation only and does not represent physical dimensions.

## Revision History Table

Drawings must include a revision history table rendered below (or adjacent to) the last view grid. The table displays the **10 most recent** revisions from the `maps` array, ordered from oldest to newest (top to bottom).

### Required Columns

| Column       | Source Field  | Description |
|-------------|--------------|-------------|
| Rev          | `rev`        | Revision identifier. |
| Date         | `date`       | ISO 8601 date. |
| Updated By   | `updated_by` | Who created this revision. |
| Comments     | `comments`   | Free-text description of changes. |

### Layout Rules

- The table has a **maximum height of 10 rows**. If the file contains more than 10 revisions, only the 10 most recent are shown.
- Each row corresponds to one map object in the `maps` array.
- The table must have visible borders separating rows and columns.
- Column widths should accommodate typical content; implementations may truncate or wrap the Comments column if space is limited.

## Custom Fields

Any custom top-level fields present in the weldb document should be rendered in a header area above the first view grid (or in a metadata block). The rendering of custom fields is left to the implementor's discretion, but they must be visible on the drawing.

## Reference Implementation

The `weldb` Python module includes a `render_monospace` function that produces an ASCII-art rendering suitable for terminal output, and a `render_pdf` function that produces a minimalistic PDF. These serve as reference implementations of this spec.
