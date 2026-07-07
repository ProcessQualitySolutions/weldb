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
| `conventional_panel_simplified_membrane_style/` | Baseline layout to copy from: vertical tubes joined by membrane bars. |
| `conventional_panel_extended_membrane_style/` | Conventional water-wall panel drawn in the extended membrane style. |
| `antler_panel/` | Conventional panel whose two outermost tubes are bent away (top welds offset). |
| `adjacent_panels/` | Two panels side by side on the same wall (consecutive tubes). |
| `stacked_panels/` | Two panels stacked vertically on the same tubes (clean seam). |
| `overlapping_panels/` | Stacked panels whose vertical coverage overlaps (same width). |
| `panel_with_clips_and_two_views/` | Cold-side attachment clips across two genuinely different views. |
| `port_panel/` | Plain-text port/opening labels (openings and inspection points, not welds). |
| `dutchman_single_tube/` | One tube's section replaced by a dutchman. |
| `dutchmen_single_tube_group/` | A few scattered single-tube dutchmen across a wide panel. |
| `dutchman_used_to_replace_failed_weld/` | A dutchman redlined in via an appended revision (append-only history). |
| `three_revision_panel/` | Append-only history across three revisions (two dutchman repairs). |
| `complex_panel/` | Every weld type on one map (extended membrane style, multi-revision). |
| `cladding_full_panel/` | A conventional panel fully clad after install. |
| `cladding_partial_panel/` | Cladding applied only over certain areas. |
| `cladding_repair/` | Existing tubes with damage repaired with cladding. |
| `large_panel/` | Large single-view water-wall panel (30 tubes, extended membrane style). |
| `transition_belt_panel/` | A mid-panel belt where alternating tubes transition. |

The MCP server exposes these through `list_examples`, `list_example_files`,
`read_example_file`, and `render_example` (renders an example to PDF).

## MCP Server

`mcp_app.py` is a **stateless, logic-only** MCP server. It holds no project state
and writes no project files: every tool takes the `.weldb` content it needs as
input and returns generated content — `.weldb`/CSV/JSON as text, and PDFs as
base64 text — for the **AI agent to save on the user's own machine**. The agent
owns all local file I/O (creating, reading, listing, moving, and deleting
`.weldb`/CSV/PDF files). The only files the server reads are its own bundled,
read-only references: the spec `.md` documents and the worked-example catalog.
This makes it safe to host online as a lightweight service.

**Saving PDFs.** The render tools (`render_pdf`, `render_revision_history`,
`render_example`) return the PDF as a base64 string in a `data` field alongside a
`filename` (`render_example` returns one such entry per PDF under `files`). To keep
a PDF, the agent decodes `data` and writes the raw bytes to `filename` as a
**binary** write — e.g. `pathlib.Path(filename).write_bytes(base64.b64decode(data))`
— never saving the base64 text itself. Each tool result also carries a `note`
spelling this out.

```bash
# Local (stdio) — one client owns the process:
python mcp_app.py
mcp run mcp_app.py

# Hosted (streamable HTTP) — many concurrent sessions:
python mcp_app.py remote --host 0.0.0.0 --port 8000
```

Remote flags (host/port/path/log-level also settable via `WELDB_*` env vars):

| Flag | Env | Default | Meaning |
|------|-----|---------|---------|
| `--host` | `WELDB_HOST` | `127.0.0.1` | Bind interface (`0.0.0.0` to accept remote connections) |
| `--port` | `WELDB_PORT` | `8000` | TCP port |
| `--path` | `WELDB_PATH` | `/mcp` | HTTP path of the streamable-HTTP endpoint |
| `--stateless` | | off | Stateless HTTP (ideal behind a load balancer — the server keeps no state either way) |
| `--json-response` | | off | Plain JSON responses instead of SSE streams |
| `--log-level` | `WELDB_LOG_LEVEL` | `INFO` | Logging level |

### Tools

| Tool | In → Out |
|------|----------|
| `create_panel` | panel params → `.weldb` YAML text to save |
| `summarize_panels` | list of `.weldb` contents → validated summary |
| `suggest_panel_name` | wall code + existing panel names → next name |
| `render_pdf` / `render_revision_history` | `.weldb` content → PDF as base64 text (`data` field) |
| `extract_weld_positions` | `.weldb` content → weld-position JSON text |
| `build_weld_csvs` | list of `.weldb` contents → point/linear/area CSV text |
| `list_docs` / `read_doc` | — → bundled spec documents |
| `list_examples` / `list_example_files` / `read_example_file` | — → bundled example catalog |
| `render_example` | example ref → PDF(s) as base64 text (`files[].data`) |

Each connecting client gets its own MCP session and the server keeps no
cross-session state, so hosting for multiple users is safe by construction — there
is no shared project directory to collide on. Install the deps with
`pip install -e ".[remote]"` (or `.[mcp]` for local stdio).

## Specs

- [drawing_spec.md](drawing_spec.md) — `.weldb` file format
- [render_spec.md](render_spec.md) — how weld maps are rendered
- [panel_naming_convention.md](panel_naming_convention.md) — panel naming
- [weld_naming_convention.md](weld_naming_convention.md) — recommended weld IDs
- [project_spec.md](project_spec.md) — project structure and file lifecycle
- [weldb_design_philosophy.md](weldb_design_philosophy.md) — design principles
