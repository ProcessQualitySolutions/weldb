# Project Specification — weldb Usage Patterns

This document describes the intended usage patterns, file management rules, and organizational guidance for `weldb` boiler repair projects (`.weldb` files).

## Who does what

**Everything in this document — maintaining the project directory, deriving CSVs, rendering PDFs, quarantining/archiving files — is done locally**, using ordinary filesystem tools and the bundled `weldb` library via the skill's scripts (`scripts/save_panel.py`, `scripts/archive_panel.py`, `scripts/build_weld_csvs.py`, `scripts/create_panel.py`). The `.weldb` YAML files are the source of truth; the CSVs and PDFs are derived artifacts — a panel's PDF is re-rendered and the project CSVs are rebuilt on every save (the CSVs carry each weld's on-drawing coordinates, so they are also the weld-position map). Where this document says "processing" happens, read it as a local operation on the user's machine.

## Purpose of weldb

`weldb` is a **document control source of truth** for weld identification and spatial layout. It is not a quality management program. YAML files define what welds exist and where they are located — nothing more. Mutable quality data such as welder IDs, weld dates, NDE results, VT results, and WPS references belong in a separate weld tracking or QC system.

`weldb` files are **static weld logs**: a single, authoritative record of the welds in a design. They are not databases for tracking fabrication or inspection activity.

## Change Tracking

Changes to YAML files are tracked **within the file itself** using the append-only `maps` array. Each revision appends a new map object with a revision identifier, date, author, and comments. The full history of layout changes is preserved in the file. The latest (last) map in the array is always the current, authoritative revision.

No external change-tracking system is required — the file is its own revision history.

## PDF Export

The agent renders PDFs locally with the `weldb` library, then writes them into the project folder. Exports follow a strict naming convention:

- The exported PDF has the **same base name** as the YAML source file, with a `.pdf` extension.
- `N5.weldb` produces `N5.pdf`.

### Always Render on Save

Saving a panel and regenerating its derived artifacts are **one operation, not two** — and there is no way to save without them. Every time a `.weldb` file is created or updated, its PDF (`<panel>.pdf`) is re-rendered **and** the project-wide weld CSVs are rebuilt in the same step, so no derived artifact can lag behind its source (`weldb.save_panel` renders the PDF; the skill's save scripts — `scripts/save_panel.py`, `scripts/create_panel*.py`, `scripts/create_panels.py` — rebuild the CSVs in the same run). See the "Always Render on Save" principle in `weldb_design_philosophy.md`. Weld coordinates live in the CSVs (`x0, y0, x1, y1` per weld, leftmost view); there is no separate `_weld_positions.json` file.

### Re-render Detection

Because saving always re-renders, PDFs do not normally fall behind. For files touched outside that flow, whether a PDF needs re-rendering can still be determined by comparing modification timestamps: if the YAML is newer than the PDF (or the PDF does not exist), re-render it. The agent applies this check itself — the server does not track or render anything.

## Weld ID Uniqueness

Weld IDs **must be unique across an entire project — but the ID that must be unique is the panel-prefixed one** (`<panel>.<weld>`), not the bare grid label. Every weld's project ID is formed by prefixing its grid label with the panel name and stripping the type prefix: grid `*T100` on panel `N5` becomes `N5.T100`. When combining welds from multiple `.weldb` files, two identical **prefixed** IDs are an error and must be rejected.

**The same grid label on different panels is NOT a collision.** Because the panel name disambiguates, two panels can carry the same weld labels without conflict. In particular, two panels that cover the same tubes at different elevations (for example `N1` and `N9`, each numbering tubes `T100`–`T103`) are perfectly valid: their welds become `N1.T100…` and `N9.T100…`. **Do not archive or rename a panel merely because another panel uses the same grid labels** — check for a duplicate *prefixed* ID (same panel *and* same weld), which only happens if the same physical weld is recorded on two panels.

After stripping the type prefix (`*`, `_`, `@`), weld base IDs must also not collide across weld types within a single file. For example, `*T205` and `_T205` sharing the base ID `T205` is an error.

**Check this with the tool, not by hand.** `scripts/validate_welds.py ./project` (library: `weldb.validate_project(dir)`) verifies all of the above across a project in one pass — panel/filename match, distinct panel names, within-file grid rules, and project-wide prefixed point-weld uniqueness — and reports every violation. Run it before deciding a weld number "already exists"; distinct panel names plus clean per-file grids already guarantee uniqueness, so there is nothing to infer.

## Project Directory Structure

A `weldb` project directory contains the active `.weldb` files at the top level, along with two special subdirectories for file lifecycle management:

```
project/
    N5.weldb
    N6.weldb
    E7.weldb
    point_welds.csv        <-- generated locally by the agent (weldb library)
    linear_welds.csv       <-- generated locally by the agent (weldb library)
    area_welds.csv         <-- generated locally by the agent (weldb library)
    quarantine/            <-- files that cause errors
    archive/               <-- cancelled or superseded scope
```

### `quarantine/`

Files that cause exceptions during loading, weld extraction, or CSV export are moved to the `quarantine/` subdirectory. This allows the rest of the project to continue processing while the problem file is isolated for investigation.

Files may be quarantined:

- **Automatically** by the agent when a file raises an exception while it is (re)generating the CSVs locally with the `weldb` library.
- **Manually** by the user or AI when a file is known to be malformed or problematic.

Quarantined files are excluded from the weld log, CSV export, and PDF rendering. To restore a quarantined file, fix the issue and move it back to the project root.

### `archive/`

Panels removed from the active scope — due to cancelled work, superseded designs, or completed teardowns — are moved to the `archive/` subdirectory rather than deleted. **A panel is archived as a whole set:** its `.weldb` source **and** all of its derived files (`<panel>.pdf`, `<panel>_revisions.pdf`) move together, so the archive holds the complete panel, not an orphaned source. Use `weldb.archive_panel` / `scripts/archive_panel.py`.

Archived files:

- Are excluded from the weld log, CSV export, and PDF rendering.
- Preserve the full revision history of the panel for audit purposes.
- May be restored to the project root if scope is reinstated.

**Never delete a panel file outright. Move it to `archive/` instead.**

Archiving is **non-destructive and batch-consistent**. Scope changes can force the same panel to be redesigned several times before its final shape is known — outside the normal append-only revision process — and a panel can be removed then re-added to scope. So archiving the same panel name more than once never overwrites an earlier archived copy: each generation is grouped under a shared suffix (`N9.*`, then `N9_1.*`, then `N9_2.*`).

### CSV Files

The agent regenerates three CSV files locally — with the `weldb` library, from all active `.weldb` files in the project directory (excluding `quarantine/` and `archive/`) — whenever the panels change:

Each row carries the weld's panel, panel-prefixed weld ID, source file, its on-drawing bounding box (`x0, y0, x1, y1` — millimetres, top-left origin, mapped in the leftmost view the weld appears in), and its resolved properties. The four coordinate columns are a **rectangle**, not two points: `(x0, y0)` is the top-left corner and `(x1, y1)` the bottom-right corner (`x0 ≤ x1`, `y0 ≤ y1`, y increasing downward).

| File | Contents |
|------|----------|
| `point_welds.csv` | One row per point weld — panel, weld ID, source file, `x0..y1`, resolved properties. Deduplicated across views and across the project. |
| `linear_welds.csv` | One row per linear weld ID — panel, weld ID, source file, `x0..y1`, resolved properties. |
| `area_welds.csv` | One row per area weld ID — panel, weld ID, source file, `x0..y1`, resolved properties. |

These files are always derived artifacts — the YAML files remain the source of truth. They also **replace the old per-panel `_weld_positions.json`**: the `x0..y1` columns are the weld-position map. Any file that causes an exception during CSV generation should be moved to `quarantine/`. (Computing the coordinate columns needs `fpdf2`; without it the CSVs still build but the `x0..y1` cells are blank.)

## Organizational Guidance

### Single Point of Responsibility

It is **strongly recommended** that a single document control person or quality manager maintain all `weldb` files for a project. Distributed editing across multiple authors without coordination risks duplicate weld IDs, inconsistent naming, and conflicting revisions.

The designated maintainer should:

- Own all YAML files for the project.
- Be the sole author of new revisions (map entries).
- Use the `weldb` weld data to **feed a separate weld tracking system** for quality management, inspection scheduling, and compliance reporting.

### weldb as an Upstream Source

`weldb` sits upstream of quality management workflows. The recommended data flow is:

```
weldb YAML files (source of truth)
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

`weldb` defines **what** is welded and **where**. Everything else — who welded it, when, how it was inspected, and whether it passed — belongs downstream.

## Core Principles

- YAML-based static weld logs.
- Append-only revision history.
- PDF export by file name.
- Project-wide weld ID uniqueness.
- Separation from quality management data.
