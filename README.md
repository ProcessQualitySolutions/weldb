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

## Install

```bash
pip install -e .
```

## Status

Early design phase — see the spec files for each standard:
- [drawing_spec_boiler.md](drawing_spec_boiler.md) / [render_spec_boiler.md](render_spec_boiler.md)
- [drawing_spec_pipeline.md](drawing_spec_pipeline.md) / [render_spec_pipeline.md](render_spec_pipeline.md)
- [drawing_spec_iron.md](drawing_spec_iron.md) / [render_spec_iron.md](render_spec_iron.md)
- [philosophy.md](philosophy.md)
