# Drawing Specification — Boiler (.weldb)

The WMDB Boiler file format uses YAML to define 2D weld map layouts for boiler repair. Each file describes the spatial arrangement of welds on a component, serving as both a human-readable drawing spec and a machine-parseable weld database.

## File Convention

WMDB Boiler files use the `.weldb` extension and are valid YAML. The `panel_name` field **must** match the filename (excluding extension). For example, a file named `N5.weldb` must contain `panel_name: N5`.

A boiler project consists of multiple `.weldb` files in the same directory, one per panel. Weld numbers must be unique across all files in a project (see Weld Rules below).

## Required Top-Level Fields

| Field        | Type   | Description |
|-------------|--------|-------------|
| `panel_name` | string | Panel identifier. Must match the filename without extension. |
| `tube_mtrl`  | string | Tube material specification (e.g., `SA-210 A1`). |
| `tube_od`    | number | Tube outside diameter. |
| `tube_wall`  | number | Tube wall thickness. |
| `units`      | string | Unit system. One of: `mm`, `ft_in`, `in`, `dec_in`, `dec_ft`. |
| `maps`       | array  | Ordered array of map objects (see below). |

## Custom Top-Level Fields

Any additional top-level fields beyond the required set are permitted. These custom fields should be rendered on drawings but are not interpreted by the core library. Use `custom_field_getter` and `custom_field_setter` to access them programmatically.

## Map Object

The `maps` array contains one or more map objects. Each map represents a snapshot of the weld layout.

| Field        | Type   | Description |
|-------------|--------|-------------|
| `rev`        | string | Revision identifier (e.g., `R0`, `R1`). |
| `date`       | string | ISO 8601 date of this revision (e.g., `2026-05-14`). |
| `updated_by` | string | Who created this revision. Arbitrary string (e.g., username, email). |
| `comments`   | string | Free-text explanation of what changed in this revision. |
| `views`      | array  | Array of view objects (see Views). |

### Append-Only Editing

Views are **never modified in place**. When a user edits the weld map, the software appends a new map object to the `maps` array with an incremented revision and the updated views. The full history of the panel's weld layout is preserved in the file. The latest (last) map in the array is the current revision.

## Views

Each map contains one or more **views**. A view represents a specific perspective of the panel — for example, the hot side and cold side of a boiler panel. Each view contains its own grid.

| Field  | Type   | Description |
|--------|--------|-------------|
| `name` | string | View identifier (e.g., `hot_side`, `cold_side`). |
| `grid` | array  | NxM list of lists of strings (see Grid Format). |

Typical views for boiler panels:
- **`hot_side`** — the fireside of the panel (furnace-facing).
- **`cold_side`** — the casing side of the panel. Items like clips are typically only welded on this side.

A panel may have one view (simple repairs) or multiple views. The number and names of views are not constrained by the spec.

## Grid Format

The `grid` field is a rectangular list of lists of strings. Every inner list must have the same length — the grid must be rectangular. Each string in the grid represents a single cell.

### Cell Types

- **Empty cell**: An empty string `""` or whitespace-only string.
- **Plain text**: Any string that does not begin with `*` or `^`. Used for labels, tube numbers, annotations, etc.
- **Point weld**: A string whose **first character** is `*` (e.g., `*W1`, `*102`). Represents a discrete weld at a single grid location.
- **Linear weld**: A string whose **first character** is `^` (e.g., `^L1`, `^S5`). Represents a segment of a continuous weld that spans multiple cells.

### Trimming

All cell strings must be trimmed of leading and trailing whitespace before interpretation. A cell containing `" 250T "` is equivalent to `"250T"`.

### Weld Rules

1. **Point welds must be unique within a view.** No two cells in a single view's grid may contain the same point-weld string. Duplicates within a view must raise an error.
2. **Point welds may appear in multiple views.** The same point weld may appear in more than one view (e.g., a tube weld visible from both hot and cold sides). When extracting welds from a file, duplicates across views are collapsed — each point weld is reported once.
3. **Point welds must be unique across a project.** When combining welds from multiple `.weldb` files, no two files may contain the same point-weld ID (after panel-number prefixing). Duplicates across files must raise an error.
4. **Linear welds may repeat.** The same linear-weld string is expected to appear in multiple cells to define the extent of a continuous weld.
5. **Embedded special characters are invalid.** If a cell string contains `*` or `^` at any position other than the first character, this is an error and must be raised when extracting welds. This prevents ambiguous labels like `tube*3` or `note^1` from silently corrupting data.
6. **Linear welds need not be contiguous.** Point welds may occupy cells between segments of the same linear weld.

## Recommended Naming Conventions

The following naming conventions are **recommended but not required**. Any string that follows the cell type rules above is valid. See `weld_naming_convention.md` for a detailed guide to the recommended naming scheme.

### Tube Welds

Point welds at tube locations. Use the tube number followed by `T` (top) or `B` (bottom):
- `*250T` — tube 250, top weld
- `*250B` — tube 250, bottom weld

### Membrane Welds

Linear welds running along membrane bars between tubes. Use sequential letters:
- `^A`, `^B`, `^C`, etc.

### Peanut Welds

Linear welds that close the gaps between tube welds in the same row. These typically occupy a single cell between two tube welds.

### Clips

Linear welds that attach clips to tubes. Clips occupy a single cell and are named with a `C` prefix followed by a letter:
- `^CA` — clip A
- `^CB` — clip B

### Ports

Plain text labels for ports, inspections, or other features. These are not welds and carry no prefix:
- `IR` — inspection port

## Example

```yaml
panel_name: N5
tube_mtrl: SA-210 A1
tube_od: 2.0
tube_wall: 0.15
units: in
client: ACME Power        # custom field

maps:
  - rev: R0
    date: 2026-05-14
    updated_by: jsmith
    comments: Initial weld map layout
    views:
      - name: hot_side
        grid:
          - [^A, "*250T", ^B, "*251T", ^C, "*252T", ^D]
          - [^A, "",      "",  "",     "",  "",      ^D]
          - [^A, "",      "",  "",     "",  "",      ^D]
          - [^A, "",      "",  "",     "",  "",      ^D]
          - [^A, "",      "",  IR,     "",  "",      ^D]
          - [^A, "",      "",  "",     "",  "",      ^D]
          - [^A, "*250B", ^E, "*251B", ^F, "*252B", ^D]
      - name: cold_side
        grid:
          - ["", "", "", "", "", "", ""]
          - ["", "", "", "", "", "", ""]
          - ["", "", "", ^CA, "", "", ""]
          - ["", "", "", "", "", "", ""]
          - ["", "", "", "", "", "", ""]
          - ["", "", "", "", "", "", ""]
          - ["", "", "", "", "", "", ""]
```
