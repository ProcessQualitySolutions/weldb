# Drawing Specification (.weldb)

The weldb file format uses YAML to define 2D weld map layouts. Each file describes the spatial arrangement of welds on a component, serving as both a human-readable drawing spec and a machine-parseable weld database.

## File Convention

weldb files use the `.weldb` extension and are valid YAML. The `panel_name` field **must** match the filename (excluding extension). For example, a file named `N5.weldb` must contain `panel_name: N5`.

A project consists of multiple `.weldb` files in the same directory, one per panel. Weld numbers must be unique across all files in a project (see Weld Rules below).

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

## Weld Property Inheritance

All top-level fields whose values are strings or numbers are **inherited by every weld** upon export. This means every point weld and linear weld in the file implicitly carries the document's `tube_mtrl`, `tube_od`, `tube_wall`, `units`, and any custom string/number fields (e.g., `client`).

Fields that are not strings or numbers (e.g., `maps`, `weld_overrides`) are never inherited.

## Weld Overrides

The optional `weld_overrides` top-level field allows overriding inherited properties for specific welds or weld types. This is useful when:

- A **header** tube has a different OD or wall thickness than the surrounding tubes.
- A **linear weld** needs a recorded `length`.
- A group of welds (e.g., clips) has different material or sizing parameters.

### Structure

```yaml
weld_overrides:
  point:                  # applies to all point welds
    tube_od: 2.0
  linear:                 # applies to all linear welds
    length: 8.5
  "_CA":                  # applies to a specific weld
    length: 6.0
    tube_od: 1.5
```

The `weld_overrides` value is a mapping. Keys are one of:

| Key        | Scope |
|------------|-------|
| `point`    | All point welds in the document. |
| `linear`   | All linear welds in the document. |
| `area`     | All area welds in the document. |
| Any weld ID (e.g., `*T250`, `_CA`, `@CL1`) | A single weld. |

Each value is a mapping of field names to override values.

### Resolution Order

When resolving the effective properties of a weld, the most specific source wins:

1. **Top-level fields** — baseline inherited by all welds.
2. **Type-level override** (`point` or `linear`) — overrides the baseline for all welds of that type.
3. **Weld-specific override** (by weld ID) — overrides everything for that individual weld.

### Standard Override Fields

| Field    | Applies To             | Type | Description |
|----------|------------------------|------|-------------|
| `length` | Linear welds, area welds | int  | Length of the weld, in the document's unit system. |
| `height` | Area welds              | int  | Height of the weld, in the document's unit system. |

Any field that appears as a top-level string or number field may also be used as an override (e.g., `tube_od`, `tube_wall`, `tube_mtrl`). Additional override-only fields like `length` and `height` are also permitted.

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

Each map contains one or more **views**. A view represents a specific perspective of the panel — for example, the hot side and cold side of a panel. Each view contains its own grid.

| Field  | Type   | Description |
|--------|--------|-------------|
| `name` | string | View identifier (e.g., `hot_side`, `cold_side`). |
| `grid` | array  | NxM list of lists of strings (see Grid Format). |

Typical views for panels:
- **`hot_side`** — the fireside of the panel (furnace-facing).
- **`cold_side`** — the casing side of the panel. Items like clips are typically only welded on this side.

A panel may have one view (simple repairs) or multiple views. The number and names of views are not constrained by the spec.

## Grid Format

The `grid` field is a rectangular list of lists of strings. Every inner list must have the same length — the grid must be rectangular. Each string in the grid represents a single cell.

### Cell Types

- **Empty cell**: An empty string `""` or whitespace-only string.
- **Plain text**: Any string that does not begin with `*`, `_`, or `@`. Used for labels, tube numbers, annotations, etc.
- **Point weld**: A string whose **first character** is `*` (e.g., `*W1`, `*102`). Represents a discrete weld at a single grid location.
- **Linear weld**: A string whose **first character** is `_` (e.g., `_L1`, `_S5`). Represents a segment of a continuous weld that spans multiple cells.
- **Area weld**: A string whose **first character** is `@` (e.g., `@CL1`, `@PAD1`). Represents a surface weld spanning multiple cells (e.g., cladding, pad welds). Behaves like a linear weld in the grid (consecutive same-ID cells merge) but carries `length` and `height` dimensions.

### Trimming

All cell strings must be trimmed of leading and trailing whitespace before interpretation. A cell containing `" T250 "` is equivalent to `"T250"`.

### Weld Rules

1. **Point welds must be unique within a view.** No two cells in a single view's grid may contain the same point-weld string. Duplicates within a view must raise an error.
2. **Point welds may appear in multiple views.** The same point weld may appear in more than one view (e.g., a tube weld visible from both hot and cold sides). When extracting welds from a file, duplicates across views are collapsed — each point weld is reported once.
3. **Point welds must be unique across a project.** When combining welds from multiple `.weldb` files, no two files may contain the same point-weld ID (after panel-number prefixing). Duplicates across files must raise an error.
4. **Linear welds may repeat.** The same linear-weld string is expected to appear in multiple cells to define the extent of a continuous weld.
5. **Embedded special characters are invalid.** If a cell string contains `*`, `_`, or `@` at any position other than the first character, this is an error and must be raised when extracting welds. This prevents ambiguous labels like `tube*3` or `note_1` from silently corrupting data.
6. **Weld IDs must not collide across types.** After stripping the prefix character (`*`, `_`, or `@`), no two welds of different types may share the same base ID. For example, `*T205` and `_T205` both have base ID `T205`, which would produce conflicting entries in the weld log. This must raise an error.
7. **Linear and area welds need not be contiguous.** Point welds may occupy cells between segments of the same linear or area weld.
8. **Area welds may repeat.** The same area-weld string is expected to appear in multiple cells to define the extent of a surface weld, like linear welds.

## Recommended Naming Conventions

The following naming conventions are **recommended but not required**. Any string that follows the cell type rules above is valid. See `weld_naming_convention.md` for a detailed guide to the recommended naming scheme.

### Tube Welds

Point welds at tube locations. Use `T` (top) or `B` (bottom) followed by the tube number:
- `*T250` — tube 250, top weld
- `*B250` — tube 250, bottom weld

### Membrane Welds

Linear welds running along membrane bars between tubes. Use sequential letters:
- `_A`, `_B`, `_C`, etc.

### Peanut Welds

Linear welds that close the gaps between tube welds in the same row. These typically occupy a single cell between two tube welds.

### Clips

Linear welds that attach clips to tubes. Clips occupy a single cell and are named with a `C` prefix followed by a letter:
- `_CA` — clip A
- `_CB` — clip B

### Cladding / Pad Welds

Area welds used for cladding or pad welding. Named with a descriptive prefix:
- `@CL1` — cladding area 1
- `@PAD1` — pad weld 1

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

weld_overrides:
  linear:
    length: 36              # default length for all linear welds
  area:
    length: 24              # default dimensions for all area welds
    height: 12
  _CA:
    length: 6               # clip A is shorter
    tube_od: 1.5            # clip welded to smaller tube

maps:
  - rev: R0
    date: 2026-05-14
    updated_by: jsmith
    comments: Initial weld map layout
    views:
      - name: hot_side
        grid:
          - [_A, "*T250", _B, "*T251", _C, "*T252", _D]
          - [_A, "",      "",  "",     "",  "",      _D]
          - [_A, "",      "",  "",     "",  "",      _D]
          - [_A, "",      "",  "",     "",  "",      _D]
          - [_A, "",      "",  IR,     "",  "",      _D]
          - [_A, "",      "",  "",     "",  "",      _D]
          - [_A, "*B250", _E, "*B251", _F, "*B252", _D]
      - name: cold_side
        grid:
          - ["", "", "", "", "", "", ""]
          - ["", "", "", "", "", "", ""]
          - ["", "", "", _CA, "", "", ""]
          - ["", "", "", "", "", "", ""]
          - ["", "", "", "", "", "", ""]
          - ["", "", "", "", "", "", ""]
          - ["", "", "", "", "", "", ""]
```
