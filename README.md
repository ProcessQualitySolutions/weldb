# weldb

Weld Map Database. A Python library for YAML-based 2D weld map drawings that double as the static weld record database, designed for **boiler repair** projects.

Boiler repair work usually lacks good engineering drawings — the panels to be replaced are typically chosen by the client, with engineering involved only in writing the repair spec. `weldb` fills that gap: a single `.weldb` file is both the 2D weld map drawing and the authoritative weld record for a panel.

## File Format

| Extension | Domain        |
|-----------|---------------|
| `.weldb`  | Boiler repair |

## Usage

```python
import weldb

doc = weldb.load("N5.weldb")
welds = weldb.get_point_welds(doc)
weldb.to_csv(welds, "welds.csv")
```

## API

- `weldb.load()` / `weldb.save()` — read/write `.weldb` YAML files
- `weldb.get_point_welds()` / `weldb.get_linear_welds()` / `weldb.get_area_welds()` — extract welds from the current map
- `weldb.resolve_weld_properties()` — resolve effective per-weld properties (with override inheritance)
- `weldb.build_weld_log()` — combine point welds from every `.weldb` file in a directory into a project-wide log
- `weldb.render_monospace()` / `weldb.render_pdf()` — render a panel to ASCII or PDF
- `weldb.to_json()` / `weldb.to_csv()` / `weldb.to_xlsx()` — export weld data
- `weldb.PointWeld` / `weldb.LinearWeld` / `weldb.AreaWeld` — weld dataclasses
- `weldb.exceptions` — error types (base: `WeldbError`)

## PDF Rendering

`render_pdf()` writes a minimalistic PDF alongside the source YAML file. The PDF has the
same filename stem with a `.pdf` extension. No revision number is embedded in the filename —
the full revision history lives inside the YAML file itself.

```python
import weldb

weldb.render_pdf("north_wall_panel_3.weldb")
# writes north_wall_panel_3.pdf in the same directory
```

Requires the optional `fpdf2` dependency: `pip install weldb[pdf]`

### PDF Freshness Rule

A PDF is considered **current** when its modification time is newer than (or
equal to) its sibling YAML file. If the YAML source (`.weldb`) is newer
than its PDF, the PDF is **stale** and must be re-rendered. In short: the PDF
should always be the younger sibling — if it's older than the YAML, re-render it.

## Install

```bash
pip install -e .          # core (YAML only)
pip install -e ".[pdf]"   # with PDF rendering support
```

## Example Catalog

The `examples/` directory is a catalog of worked `.weldb` panels, organized into
one folder per arrangement so an AI assistant can pick the closest match before
constructing a new weld map. Each file opens with a comment block explaining how
its grid is laid out.

| Folder | Demonstrates |
|--------|--------------|
| `conventional_panel/` | Baseline layout: vertical tubes joined by membrane bars. |
| `antler_panel/` | Conventional panel with the outermost tubes bent out (top welds offset to the side and lower). |
| `adjacent_panels/` | Two panels side by side on the same wall (consecutive tubes). |
| `stacked_panels/` | Two panels stacked vertically on the same tubes (clean seam). |
| `overlapping_panels/` | Stacked panels whose vertical coverage overlaps (same width). |
| `panel_with_clips/` | Cold-side attachment clips (`_CA`, `_CB`, ...). |
| `port_panel/` | Plain-text port/opening labels (`IR`, `OBS`). |
| `single_tube_dutchman/` | One tube's section replaced by a dutchman (`*B…DT`/`*B…DB`). |
| `single_tube_dutchman_group/` | Many single-tube dutchmen across a wide panel; every membrane replaced full-length. |
| `panel_with_repair_dutchman/` | A dutchman redlined in via an appended revision (append-only history). |
| `two_view_panel/` | Two genuinely different views: hot-side welds plus cold-side clips. |
| `three_revision_panel/` | Append-only history across three revisions (two dutchman repairs). |
| `complex_panel/` | Every weld type on one map: point, membrane/peanut, an area (cladding) weld, and a port. |
| `transition_belt_panel/` | A belt transition splits each tube column with `*BTT…`/`*BTB…` welds. |

The MCP server exposes these through `list_examples`, `list_example_files`,
`read_example_file`, and `render_example` (renders an example to PDF).

## Specs

- [drawing_spec.md](drawing_spec.md) — `.weldb` file format
- [render_spec.md](render_spec.md) — how weld maps are rendered
- [panel_naming_convention.md](panel_naming_convention.md) — panel naming
- [weld_naming_convention.md](weld_naming_convention.md) — recommended weld IDs
- [project_spec.md](project_spec.md) — project structure and file lifecycle
- [philosophy.md](philosophy.md) — design principles
