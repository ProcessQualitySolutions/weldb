# Render Specification — Boiler (.weldb)

This document defines how WMDB Boiler weld maps must be rendered visually, whether on the web, in a terminal, or in print. Implementations must follow these rules to ensure consistent, unambiguous weld map drawings.

## Prefix Characters

Only two weld prefix characters exist. No other prefix characters are permitted in the drawing.

| Weld Type    | Prefix | Description |
|-------------|--------|-------------|
| Point weld  | `*`    | Discrete weld at a single location. |
| Linear weld | `_`    | Segment of a continuous weld spanning multiple cells. |

The prefix characters (`*` and `_`) are part of the weld label and **are rendered as-is** in the output. No substitution or icon replacement is performed.

Non-weld text cells (tube labels, annotations, etc.) are rendered as plain text with no prefix.

## Multi-View Rendering

Each map may contain multiple views (e.g., `hot_side`, `cold_side`). Each view must be rendered as a separate grid with its own label.

### View Label

Above each grid, render a **view label** showing the view name in a readable format. For example, a view named `hot_side` should display as `HOT SIDE` or `Hot Side`. The label must be visually distinct from the grid content (e.g., bold, uppercase, or underlined in monospace).

### View Order

Views are rendered in the order they appear in the `views` array. Each view's grid is rendered independently using the same cell rendering rules below.

### Spacing

A blank line or visual separator must appear between consecutive view grids to clearly distinguish them.

## Cell Rendering Rules

### Point Welds

- Each point weld cell must have a **visible border on all four sides**.
- Display the cell value as-is (e.g., `*W1`).

### Linear Welds

- Consecutive cells in the **same row** that share the same linear weld ID must be **visually merged** into a single span.
- The merged span has **exterior borders only** — no internal cell borders within the span.
- The weld label appears **once** in the merged span, not repeated per cell.
- Display the cell value as-is (e.g., `_L1`).
- Linear weld cells that are **not adjacent** (e.g., separated by a point weld) form separate visual spans, each labeled independently.

### Plain Text Cells

- No prefix, no special borders beyond the default grid lines.
- Rendered as-is.

### Empty Cells

- Rendered as blank space within the grid.

## Color

Drawings **must not rely on color coding** to convey information. Color may be used as a supplementary visual aid (e.g., highlighting), but all information must be legible in monochrome.

## Legend

All rendered drawings **must include a legend** explaining the prefix characters. The legend must appear in the margins or footer of the drawing and contain at minimum:

- `*` = Point weld (discrete weld at a single location)
- `_` = Linear weld (continuous weld spanning multiple cells)

The legend must be present on every rendered page or sheet that contains a weld map grid.

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

Any custom top-level fields present in the WMDB Boiler document should be rendered in a header area above the first view grid (or in a metadata block). The rendering of custom fields is left to the implementor's discretion, but they must be visible on the drawing.

## Reference Implementation

The `wmdb.boiler` Python module includes a `render_monospace` function that produces an ASCII-art rendering suitable for terminal output, and a `render_pdf` function that produces a minimalistic PDF. These serve as reference implementations of this spec.
