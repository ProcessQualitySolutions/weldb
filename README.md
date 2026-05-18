# wmdb

Weld Map Database. A multi-standard Python library for YAML-based 2D weld map drawings that double as the static weld record database.

## Standards

| Module          | Extension | Domain                      | Status      |
|----------------|-----------|-----------------------------|-------------|
| `wmdb.boiler`  | `.weldb`  | Boiler repair               | In progress |
| `wmdb.pipeline`| `.weldp`  | Pipeline                    | Placeholder |
| `wmdb.iron`    | `.weldi`  | Structural steel (iron)     | Placeholder |

## Usage

```python
import wmdb.boiler as boiler
from wmdb.export import to_csv

doc = boiler.load("north_wall_panel_3.weldb")
welds = boiler.get_point_welds(doc)
to_csv(welds, "welds.csv")
```

## Shared Utilities

- `wmdb.types` — `PointWeld`, `LinearWeld` dataclasses shared across all standards
- `wmdb.export` — `to_json()`, `to_csv()`, `to_xlsx()` for any standard's weld data
- `wmdb.exceptions` — shared error types

## PDF Rendering

Each standard provides a `render_pdf()` function that writes a minimalistic PDF
alongside the source YAML file. The PDF has the same filename stem with a `.pdf`
extension. No revision number is embedded in the filename — the full revision
history lives inside the YAML file itself.

```python
import wmdb.boiler as boiler

boiler.render_pdf("north_wall_panel_3.weldb")
# writes north_wall_panel_3.pdf in the same directory
```

Requires the optional `fpdf2` dependency: `pip install wmdb[pdf]`

### PDF Freshness Rule

A PDF is considered **current** when its modification time is newer than (or
equal to) its sibling YAML file. If the YAML source (e.g., `.weldb`) is newer
than its PDF, the PDF is **stale** and must be re-rendered. In short: the PDF
should always be the younger sibling — if it's older than the YAML, re-render it.

## Install

```bash
pip install -e .          # core (YAML only)
pip install -e ".[pdf]"   # with PDF rendering support
```

## Status

Early design phase — see the spec files for each standard:
- [drawing_spec_boiler.md](drawing_spec_boiler.md) / [render_spec_boiler.md](render_spec_boiler.md)
- [drawing_spec_pipeline.md](drawing_spec_pipeline.md) / [render_spec_pipeline.md](render_spec_pipeline.md)
- [drawing_spec_iron.md](drawing_spec_iron.md) / [render_spec_iron.md](render_spec_iron.md)
- [philosophy.md](philosophy.md)
