# Project Specification — WMDB Usage Patterns

This document describes the intended usage patterns, file management rules, and organizational guidance for all three WMDB standards: Boiler (`.weldb`), Pipeline (`.weldp`), and Iron (`.weldi`).

## Purpose of WMDB

WMDB is a **document control source of truth** for weld identification and spatial layout. It is not a quality management program. YAML files define what welds exist and where they are located — nothing more. Mutable quality data such as welder IDs, weld dates, NDE results, VT results, and WPS references belong in a separate weld tracking or QC system.

WMDB files are **static weld logs**: a single, authoritative record of the welds in a design. They are not databases for tracking fabrication or inspection activity.

## Change Tracking

Changes to YAML files are tracked **within the file itself** using the append-only `maps` array. Each revision appends a new map object with a revision identifier, date, author, and comments. The full history of layout changes is preserved in the file. The latest (last) map in the array is always the current, authoritative revision.

No external change-tracking system is required — the file is its own revision history.

## PDF Export

PDF exports follow a strict naming convention:

- The exported PDF has the **same base name** as the YAML source file, with a `.pdf` extension.
- `N5.weldb` produces `N5.pdf`.
- `MAIN-LINE.weldp` produces `MAIN-LINE.pdf`.
- `PLATFORM-A.weldi` produces `PLATFORM-A.pdf`.

### Re-render Detection

Whether a PDF needs to be re-rendered can be determined by comparing the modification timestamps of the YAML source file and its corresponding PDF. If the YAML file is newer than the PDF (or the PDF does not exist), the PDF must be re-rendered. If the PDF is the same age or newer than the YAML file, no re-render is needed.

## Weld ID Uniqueness

Weld IDs **must be unique across an entire project**, not just within a single file. When combining welds from multiple files (e.g., multiple `.weldb` panel files in a boiler project), duplicate weld IDs across files are an error and must be rejected.

This rule applies to all three standards:

| Standard | Scope of uniqueness |
|----------|-------------------|
| Boiler (`.weldb`) | All `.weldb` files in the project directory. |
| Pipeline (`.weldp`) | All `.weldp` files in the project directory. |
| Iron (`.weldi`) | All `.weldi` files in the project directory. |

After stripping the type prefix (`*`, `_`, `@`), weld base IDs must also not collide across weld types within a file. For example, `*T205` and `_T205` sharing the base ID `T205` is an error.

## Project Directory Structure

A WMDB project directory contains the active YAML files at the top level, along with two special subdirectories for file lifecycle management:

```
project/
    N5.weldb
    N6.weldb
    E7.weldb
    point_welds.csv        <-- auto-generated at MCP server startup
    linear_welds.csv       <-- auto-generated at MCP server startup
    area_welds.csv         <-- auto-generated at MCP server startup
    quarantine/            <-- files that cause errors
    archive/               <-- cancelled or superseded scope
```

### `quarantine/`

Files that cause exceptions during loading, weld extraction, or CSV export are moved to the `quarantine/` subdirectory. This allows the rest of the project to continue processing while the problem file is isolated for investigation.

Files may be quarantined:

- **Automatically** by the MCP server when a file raises an exception during startup CSV generation.
- **Manually** by the user or AI when a file is known to be malformed or problematic.

Quarantined files are excluded from the weld log, CSV export, and PDF rendering. To restore a quarantined file, fix the issue and move it back to the project root.

### `archive/`

Panels removed from the active scope — due to cancelled work, superseded designs, or completed teardowns — are moved to the `archive/` subdirectory rather than deleted.

Archived files:

- Are excluded from the weld log, CSV export, and PDF rendering.
- Preserve the full revision history of the panel for audit purposes.
- May be restored to the project root if scope is reinstated.

Never delete a panel file outright. Move it to `archive/` instead.

### CSV Files

The MCP server regenerates three CSV files at startup by loading all active `.weldb` files in the project directory (excluding `quarantine/` and `archive/`):

| File | Contents |
|------|----------|
| `point_welds.csv` | One row per point weld — panel, weld ID, grid position, source file. Deduplicated across views. |
| `linear_welds.csv` | One row per linear weld ID — panel, weld ID, cell count, source file. |
| `area_welds.csv` | One row per area weld ID — panel, weld ID, cell count, source file. |

These files are always derived artifacts — the YAML files remain the source of truth. Any file that causes an exception during CSV generation is automatically moved to `quarantine/`.

## Organizational Guidance

### Single Point of Responsibility

It is **strongly recommended** that a single document control person or quality manager maintain all WMDB files for a project. Distributed editing across multiple authors without coordination risks duplicate weld IDs, inconsistent naming, and conflicting revisions.

The designated maintainer should:

- Own all YAML files for the project.
- Be the sole author of new revisions (map entries).
- Use the WMDB weld data to **feed a separate weld tracking system** for quality management, inspection scheduling, and compliance reporting.

### WMDB as an Upstream Source

WMDB sits upstream of quality management workflows. The recommended data flow is:

```
WMDB YAML files (source of truth)
    |
    +--> PDF drawings (visual reference)
    |
    +--> Export (JSON / CSV / XLSX)
            |
            +--> Weld tracking system (welder IDs, dates, NDE, VT, WPS)
            |
            +--> Inspection records
            |
            +--> Compliance reporting
```

WMDB defines **what** is welded and **where**. Everything else — who welded it, when, how it was inspected, and whether it passed — belongs downstream.

## Standards Summary

| Standard | Extension | Status | Description |
|----------|-----------|--------|-------------|
| Boiler | `.weldb` | Active | Boiler repair weld maps. Multi-view, multi-panel projects. |
| Pipeline | `.weldp` | Placeholder | Pipeline construction and repair. Not yet defined. |
| Iron | `.weldi` | Placeholder | Structural steel construction and repair. Not yet defined. |

All three standards share the same core principles: YAML-based static weld logs, append-only revision history, PDF export by file name, project-wide weld ID uniqueness, and separation from quality management data.
