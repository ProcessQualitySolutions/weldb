# Panel Naming Convention

Panel names should be short, descriptive identifiers that encode the wall location and sequence number. Brevity is essential — panel names are prepended to every weld ID in the project weld log.

## Structure

```
<wall><number>
```

| Component | Format | Description |
|-----------|--------|-------------|
| Wall | 1-2 letter code | Location in the unit (see Wall Codes below). |
| Number | integer | Sequential panel number on that wall, starting at 1. |

## Wall Codes

| Code | Meaning |
|------|---------|
| `N` | North wall |
| `S` | South wall |
| `E` | East wall |
| `W` | West wall |
| `T` | Top / ceiling |
| `F` | Floor |
| `LS` | Lower slope |
| `US` | Upper slope |
| `H` | Header |
| `TB` | Transition belt |
| `NE` | Northeast corner |
| `NW` | Northwest corner |
| `SE` | Southeast corner |
| `SW` | Southwest corner |
| `D` | Division wall |
| `BN` | Bullnose |

## Examples

| Panel Name | Meaning |
|------------|---------|
| `N5` | North wall, panel 5 |
| `W3` | West wall, panel 3 |
| `LS2` | Lower slope, panel 2 |
| `H1` | Header, panel 1 |
| `TB4` | Transition belt, panel 4 |
| `NE1` | Northeast corner, panel 1 |
| `T7` | Ceiling, panel 7 |
| `D2` | Division wall, panel 2 |

## Directional Disambiguation

Some locations (lower slope, upper slope, transition belt, bullnose, division wall) may exist on more than one side of the unit. When disambiguation is needed, prepend a cardinal direction to the wall code:

| Code | Meaning |
|------|---------|
| `WLS` | West lower slope |
| `ELS` | East lower slope |
| `NTB` | North transition belt |
| `STB` | South transition belt |
| `NBN` | North bullnose |
| `SBN` | South bullnose |
| `ND` | North division wall |
| `SD` | South division wall |

Use the bare code (`LS`, `TB`, `BN`, `D`) when there is only one of that feature in the unit. Add the directional prefix only when two or more exist and must be distinguished.

## Guidelines

- Keep names as short as possible. Every character appears in every weld ID in the log.
- Number panels sequentially per wall. If the north wall has panels N1 through N6, the next panel is N7.
- Do not reuse panel numbers on the same wall, even if a panel is removed from the project.
- Wall codes are case-sensitive. Use uppercase only.
- This convention is recommended but not enforced by the library. Any string is a valid `panel_name`.
