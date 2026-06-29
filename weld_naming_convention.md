# Weld Naming Convention — Panels

This document describes the **recommended** naming convention for point welds in panel repair projects. This convention is **not part of the weldb standard** and is not enforced by the library. Any string that follows the cell type rules in `drawing_spec.md` is valid.

This convention is intended for simple panel repairs and is also used by AI agents generating weld maps.

## Scope — what belongs in a weld name

A `.weldb` file records **what welds exist and where**. Only **physical changes to the panel** — such as installing a dutchman (replacement section) — are redlined into the file, because they change the set of welds.

Weld **quality history** — repairs, reworks, and cutouts on an existing weld — is **not** tracked here. That belongs in the weld management / QC system. A weld that is repaired keeps the same weld ID in the weldb file; the repair is recorded downstream. Consequently, the only suffix in this convention is the dutchman suffix.

## Structure

A weld name is built from the following components, concatenated without separators:

```
<panel><side><tube>[<dutchman_suffix>]
```

| Component        | Format     | Required | Description |
|------------------|------------|----------|-------------|
| Panel            | string     | Yes      | Panel identifier (e.g., `N5` for north panel 5). |
| Side             | `T` or `B` | Yes      | `T` = top (weld at top of tube), `B` = bottom (weld at bottom of tube). |
| Tube             | number     | Yes      | Tube number (e.g., `100`). |
| Dutchman suffix  | see below  | No       | Appended when a dutchman (replacement piece) is installed. |

## Side Codes

| Code | Meaning |
|------|---------|
| `T`  | Top — weld at the top of the tube. |
| `B`  | Bottom — weld at the bottom of the tube. |

## Dutchman Suffixes

When a dutchman (replacement tube section) is installed, append a direction suffix indicating which end of the dutchman the weld is on. A dutchman creates two welds — one at each end of the replacement piece.

### Vertical tubes

| Suffix | Meaning |
|--------|---------|
| `DT`   | Dutchman top — weld at the top of the dutchman. |
| `DB`   | Dutchman bottom — weld at the bottom of the dutchman. |

### Flat / horizontal orientation

Use cardinal directions when the tube orientation is flat or horizontal:

| Suffix | Meaning |
|--------|---------|
| `DN`   | Dutchman north. |
| `DS`   | Dutchman south. |
| `DE`   | Dutchman east. |
| `DW`   | Dutchman west. |

## Examples

All examples below are for **north panel 5, tube 100** (`N5`):

| Weld Name   | Meaning |
|-------------|---------|
| `N5T100`    | Top weld on tube 100. |
| `N5B100`    | Bottom weld on tube 100. |
| `N5B100DT`  | Bottom weld on tube 100, dutchman top. |
| `N5B100DB`  | Bottom weld on tube 100, dutchman bottom. |
| `N5B100DN`  | Bottom weld on tube 100, dutchman north (flat orientation). |

## Notes

- This convention is designed for simple panel repairs. Complex projects may need a different scheme.
- The panel identifier is prepended by the `build_weld_log` utility when combining welds from multiple `.weldb` files, joined with a period (`.`) separator. Individual weld map grids therefore use the weld name **without** the panel prefix (e.g., `*B100DT` in the grid, which becomes `N5.B100DT` in the weld log).
- Repairs, reworks, and cutouts are **not** encoded in the weld name. A repaired weld keeps its original ID; the repair is tracked in the weld management system, not in the weldb file.
