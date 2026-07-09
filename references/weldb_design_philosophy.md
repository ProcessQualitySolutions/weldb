# Philosophy

A single YAML file should be both the 2D graphical representation of a boiler repair weld map and the authoritative weld record database. The weld records themselves are static — mutable inspection and QC data (NDE, VT, weld date, WPS, welder ID) live in separate QC records, not in the weld map files. This separation keeps the map clean and the data auditable.

## Only the Current Map Produces Welds

The `maps` array preserves the full revision history of a panel's weld layout, but **only the latest (last) map is authoritative**. Weld extraction functions (`get_point_welds`, `get_linear_welds`) always operate on the last map — historical maps exist solely for viewing how the layout changed over time and must never be used to generate weld records.

## Always Render on Save

The `.weldb` YAML is the single source of truth; the drawing PDF and the weld
CSVs are **derived artifacts**. A derived artifact that lags behind its source is
worse than no artifact — it silently misrepresents the panel. So the standard is:
**a panel is never saved without its artifacts, and there is no opt-out.** Every
create or update writes the `.weldb`, immediately re-renders its PDF, and rebuilds
the project weld CSVs in the same operation (`weldb.save_panel` renders the PDF;
the skill's save scripts — `scripts/save_panel.py` and the `create_panel*` /
`create_panels.py` scaffolds — rebuild the CSVs in the same run). This is one
operation, not a save followed by a remembered "now go render" step — the pieces
cannot drift apart because they never happen apart. The CSVs also hold each weld's
on-drawing coordinates (`x0, y0, x1, y1`, mapped in the leftmost view the weld
appears in), so they *are* the weld-position map — there is no separate per-panel
position file.

## Archive, Don't Delete

A panel file is a record, and records are not deleted. When a panel leaves active
scope — cancelled, superseded, or torn down — it is **archived, not removed**: its
`.weldb` and every derived file move together into `archive/`, preserving the full
revision history for audit. Because scope changes can force the same panel to be
redesigned several times before its final shape is known (outside the normal
append-only revision process), archiving is non-destructive and batch-consistent:
repeated archives of the same panel name are kept as distinct, grouped generations
rather than overwriting one another.

## Opinionated by Design

This library is not a general-purpose toolkit for working with weld data. It is the reference implementation of a strict construction and repair drawing standard. The goal is a minimalistic, standardized, deterministic weld database that prevents errors — not a flexible framework that accommodates every possible workflow. Where the spec is prescriptive, the library enforces it; where the spec is silent, the library does nothing.
