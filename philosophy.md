# Philosophy

A single YAML file should be both the 2D graphical representation of a boiler repair weld map and the authoritative weld record database. The weld records themselves are static — mutable inspection and QC data (NDE, VT, weld date, WPS, welder ID) live in separate QC records, not in the weld map files. This separation keeps the map clean and the data auditable.

## Only the Current Map Produces Welds

The `maps` array preserves the full revision history of a panel's weld layout, but **only the latest (last) map is authoritative**. Weld extraction functions (`get_point_welds`, `get_linear_welds`) always operate on the last map — historical maps exist solely for viewing how the layout changed over time and must never be used to generate weld records.

## Opinionated by Design

This library is not a general-purpose toolkit for working with weld data. It is the reference implementation of a strict construction and repair drawing standard. The goal is a minimalistic, standardized, deterministic weld database that prevents errors — not a flexible framework that accommodates every possible workflow. Where the spec is prescriptive, the library enforces it; where the spec is silent, the library does nothing.
