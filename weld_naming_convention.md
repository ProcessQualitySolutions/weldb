# Weld Naming Convention — Boiler Panels

This document describes the **recommended** naming convention for point welds in boiler panel repair projects. This convention is **not part of the weldb standard** and is not enforced by the library. Any string that follows the cell type rules in `drawing_spec_boiler.md` is valid.

This convention is intended for simple boiler panel repairs and is also used by AI agents generating weld maps.

## Structure

A weld name is built from the following components, concatenated without separators:

```
<panel><side><tube>[<repair_code>][<dutchman_suffix>]
```

| Component          | Format    | Required | Description |
|-------------------|-----------|----------|-------------|
| Panel             | string    | Yes      | Panel identifier (e.g., `N5` for north panel 5). |
| Side              | `T` or `B` | Yes    | `T` = top (weld at top of tube), `B` = bottom (weld at bottom of tube). |
| Tube              | number    | Yes      | Tube number (e.g., `100`). |
| Repair code       | see below | No       | Appended when the weld has been repaired, reworked, or cut out. |
| Dutchman suffix   | see below | No       | Appended when a dutchman (replacement piece) is installed. |

## Side Codes

| Code | Meaning |
|------|---------|
| `T`  | Top — weld at the top of the tube. |
| `B`  | Bottom — weld at the bottom of the tube. |

## Repair Codes

Repair codes are appended sequentially when work is performed on a weld.

| Code   | Meaning |
|--------|---------|
| `R1`, `R2`, ... | Repair. Sequential repair attempts on the same weld. |
| `RW1`, `RW2`, ... | Rework. When rework (not a full repair) is needed. |
| `C1`, `C2`, ...  | Cutout. Quality-related cutout of the weld. |

## Dutchman Suffixes

When a dutchman (replacement tube section) is installed, append a direction suffix indicating which end of the dutchman the weld is on.

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

| Weld Name      | Meaning |
|---------------|---------|
| `N5T100`       | Top weld on tube 100, original. |
| `N5T100R1`     | Top weld on tube 100, first repair. |
| `N5T100C2`     | Top weld on tube 100, second cutout. |
| `N5B100C1R2`   | Bottom weld on tube 100, first cutout, second repair. |
| `N5B100DT`     | Bottom weld on tube 100, dutchman top. |
| `N5B100DBR1`   | Bottom weld on tube 100, dutchman bottom, first repair. |

## Notes

- This convention is designed for simple boiler panel repairs. Complex projects may need a different scheme.
- The panel identifier is prepended by the `build_weld_log` utility when combining welds from multiple `.weldb` files, so individual weld map grids use the weld name **without** the panel prefix (e.g., `*T100R1` in the grid, which becomes `N5-T100R1` in the weld log).
- Repair codes and dutchman suffixes can be combined (e.g., `DBR1` = dutchman bottom, first repair).
- When multiple codes apply, the order is: side, tube, cutout/repair, dutchman, repair on dutchman.
