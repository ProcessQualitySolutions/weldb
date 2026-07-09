---
name: weldb
description: >-
  Create, edit, render, and export boiler-repair weld maps stored as .weldb YAML
  files. Use when the user works with .weldb files or boiler panel weld maps:
  generating a panel scaffold, laying out tubes/membranes/welds, producing an
  engineering-drawing PDF, exporting weld CSVs, computing a weld-position
  coordinate map, or building an interactive editor for a weld map. Bundles the
  weldb Python library, so no pip install or network access is required.
license: MIT
---

# weldb — Boiler Weld Map Skill

A `.weldb` file is a single YAML document that is **both** the 2D weld-map
drawing **and** the authoritative static weld record for a boiler-repair panel:
its properties, an append-only revision history (`maps`), and one or more views
whose grids lay out the tubes, membranes, and welds. This skill helps you author
those files and process them.

The **`weldb` Python library is bundled** under `src/` — every script adds it to
`sys.path` itself, so nothing needs to be pip-installed. (To import it yourself:
`import sys; sys.path.insert(0, "src"); import weldb`.)

## Learn the format first

Before constructing or editing a map, read the relevant reference (they are
plain bundled files — open them directly):

| File | Covers |
|------|--------|
| `references/drawing_spec.md` | The `.weldb` format: required/optional fields, weld_overrides, grid cell types, weld rules. **Start here.** |
| `references/render_spec.md` | How a map is drawn (merging, tallies, legend, revision table). |
| `references/panel_naming_convention.md` | Panel names (wall code + number). |
| `references/weld_naming_convention.md` | Recommended weld IDs (tube T/B, dutchman suffixes). |
| `references/project_spec.md` | Project layout, weld-ID uniqueness, file lifecycle. |
| `references/weldb_design_philosophy.md` | Why the format is the way it is. |

## Worked examples

`examples/` is a catalog of real arrangements (adjacent, stacked, overlapping,
clips, ports, dutchmen, cladding, transitions, multi-revision, …). Pick the
closest match to what the user describes and copy from it.

```bash
python scripts/list_examples.py                 # list arrangements + descriptions
python scripts/list_examples.py -e adjacent_panels
cat examples/adjacent_panels/N5.weldb           # read one directly
```

## Scripts

Run these with the bundled library — no install needed (PDF/weld-position scripts
additionally need `fpdf2`; `pip install fpdf2` if it's missing).

| Script | Does |
|--------|------|
| `scripts/create_panel_extended_membrane.py` | Generate a conventional panel **scaffold** in the **extended** membrane style, **and render it** (see below). **Prefer this.** |
| `scripts/create_panel.py` | Same, but the **simplified** membrane style. Use only if the user asks for it. |
| `scripts/create_panels.py` | **Create + render MANY panels from one JSON spec, in one process.** Use for stacked/adjacent/overlapping sets (see **Creating multiple panels**). |
| `scripts/save_panel.py` | **Save a panel and render ALL its artifacts in one shot** — validate + write the `.weldb`, then its PDF and weld-position JSON. **Use this after every edit** (see **Always render on save**). |
| `scripts/archive_panel.py` | Retire a panel: **move** its `.weldb` + `.pdf` + `.json` together into `archive/` (never delete — see **Archive, don't delete**). |
| `scripts/render_pdf.py` | Render a panel to a single-sheet engineering-drawing PDF only (**color by default**). |
| `scripts/render_revision_history.py` | Render the full revision history to a standalone PDF. |
| `scripts/build_weld_csvs.py` | Point/linear/area weld CSVs (with resolved properties) from files/dirs. |
| `scripts/weld_positions.py` | JSON coordinate map of every weld on the rendered PDF (optional canvas pixels). |
| `scripts/regenerate_artifacts.py` | Bulk re-sync a whole project: re-render each changed panel's PDF + weld-position map and rebuild the CSVs. Skips panels already up to date (`--force` to override). |
| `scripts/list_examples.py` | Browse the bundled example catalog. |

Every script has `--help`.

## Always render on save

**A `.weldb` file is never saved without its derived artifacts.** The `.weldb`
YAML is the source of truth; its PDF (`<panel>.pdf`) and weld-position map
(`<panel>_weld_positions.json`) are derived, and they must never lag behind it.
So **every create or update renders them in the same step** — one command, one
round trip, no stale artifacts:

```bash
# After editing a .weldb (with the Write/Edit tools or by hand), save+render it:
python scripts/save_panel.py N5.weldb                       # -> N5.weldb (validated) + N5.pdf + N5_weld_positions.json
python scripts/save_panel.py N5.weldb --canvas-w 1000 --canvas-h 800   # + pixel coords in the JSON
python scripts/save_panel.py N5.weldb --revisions           # also N5_revisions.pdf

# One-shot create: pipe YAML in and it is written AND rendered together:
python scripts/save_panel.py N5.weldb --stdin < draft.yaml
```

`save_panel.py` also **round-trip-validates** the YAML (so a hand-tweak can't
corrupt it), replacing the separate validation step. The `create_panel*` scripts
render on save too, so a fresh scaffold already has its PDF and JSON. Prefer
`save_panel.py` for a single panel; use `regenerate_artifacts.py` only to re-sync
a whole directory in bulk. (All rendering needs `fpdf2`; if it is missing the
`.weldb` is still written and the PDF/JSON are skipped with a warning — install
it with `pip install fpdf2`, or build an HTML artifact instead.)

## Creating a panel

1. Read `references/drawing_spec.md` and the closest `examples/` arrangement.
2. Determine the panel name from `references/panel_naming_convention.md` (wall
   code + next sequential number — read the user's existing `.weldb` files to
   continue the sequence). Confirm material, OD, wall, units, elevation, and the
   tube range with the user.
3. Scaffold it. **Use the extended membrane style by default** — run
   `create_panel_extended_membrane.py`. Only use `create_panel.py` (simplified
   style) if the user specifically asks for the simplified/basic look.
   ```bash
   python scripts/create_panel_extended_membrane.py N5 --mtrl "SA-210 A1" \
       --od 2.0 --wall 0.15 --units in --elevation "1850 in" \
       --tube-start 250 --tube-end 254
   ```
   The scaffold command **renders on save**, so `N5.weldb`, `N5.pdf`, and
   `N5_weld_positions.json` all appear together.
4. **The scaffold is the conventional layout only — not a finished panel.** Edit
   the generated YAML to match what the user actually described: add ports,
   clips, cladding/area welds, dutchman repairs, weld-length overrides,
   dropped/offset tubes, extra views, or custom fields. Then **save+render it in
   one shot** — this re-validates the YAML (a hand-tweak can't corrupt it) and
   refreshes the PDF and weld-position JSON together:
   `python scripts/save_panel.py N5.weldb`.

### Panel conventions

- **Views: hot side only.** A normal panel needs just the `hot_side` view (the
  scaffold makes only that). Add a `cold_side` or any other view **only when the
  user asks** for more or different views (`--cold-side`, `--view NAME`, or by
  editing the YAML). Clips, for example, usually live on a cold-side view — add
  it then.
- **Tube numbering.** Tubes are numbered **left → right as seen from the hot
  side** (`--tube-start` is the leftmost tube). Any **reverse/back view** (seen
  from behind) must number its tubes in the **reverse** order, because left and
  right swap when you look from the other side.
- **Membrane style.** Default to the **extended** membrane style (membranes drawn
  running past the welds) unless the user asks for the simplified style.

## Creating multiple panels

When the user asks for several panels at once, **create them all from one JSON
spec in a single process** with `create_panels.py` — one interpreter start, one
round trip, and every panel rendered on save. Prefer this over calling the
single-panel scaffold once per panel.

```bash
python scripts/create_panels.py --spec panels.json --out-dir ./project
# or pipe the spec on stdin:
python scripts/create_panels.py --out-dir ./project < panels.json
```

The spec is a JSON array of panel objects (underscored keys mirroring the
single-panel options — `panel_name`, `mtrl`, `od`, `wall`, `units`, `elevation`,
`tube_start`, `tube_end`, plus optional `style`, `cold_side`, `views`, `fields`,
…); see `create_panels.py --help`. The whole spec is validated before anything is
written, so a bad entry aborts the batch cleanly.

**This bulk flow is ideal for panels that belong together — `stacked` (one above
another on the same tubes), `adjacent` (side by side on the same wall), and
`overlapping` panels** — because they are designed as a set. Whenever you lay out
stacked, adjacent, or overlapping panels, **understand which tube and membrane
welds are shared across the boundary**: a weld at the seam between two panels is
**one** physical weld and must be recorded on **one** panel only (weld IDs are
unique project-wide — see `references/project_spec.md`). Never duplicate a shared
boundary weld onto both panels. Study the `adjacent_panels`, `stacked_panels`, and
`overlapping_panels` examples before laying out a set.

After scaffolding a set, remember to [present the PDFs](#present-the-pdf-to-the-user):
for a multi-panel request, list the panels with a link/path to each PDF rather
than dumping them all inline.

## Prefer one process over many

Every script call pays Python + `fpdf2` startup, and every call is a round trip.
So collapse work into as few invocations as possible: use `save_panel.py` (save +
render together) instead of chaining `render_pdf.py` + `weld_positions.py`;
`create_panels.py` for a set instead of N single creates; and
`regenerate_artifacts.py` for a whole-directory re-sync. (In library code,
`weldb.render_panel_bundle(doc)` renders the PDF **and** the weld-position map in a
single layout pass.)

## Editing a map visually

Two options:

- **Interactive HTML editor (recommended, works in a headless sandbox).** Build
  the user a self-contained HTML artifact that renders each view's grid as
  colored, editable cells and exports updated `.weldb` YAML. Full guide and a
  ready-to-adapt template: **`references/html_artifact_editor.md`**.
- **Desktop editor (advanced, local machine only).** `weldb_visual_editor.py` is
  a Tkinter app — a live YAML + editable-grid editor
  (`python weldb_visual_editor.py N5.weldb`). It needs a display, so it does
  **not** run in a headless sandbox; use the HTML artifact there instead.

## Present the PDF to the user

**After generating or modifying a panel, always show the user its PDF** — the PDF
is the human-readable deliverable, so surface it (or a link/path to it) every time
you create or change a panel. **Exception:** if the user asked for **multiple**
panels at once, don't dump every PDF inline — instead **list the generated panels
with a link/path to each panel's PDF**.

## Keep derived artifacts in sync

The `.weldb` YAML is always the source of truth; PDFs, weld-position maps, and
CSVs are **derived artifacts** that must never lag behind it. The primary way to
keep them in sync is **[always render on save](#always-render-on-save)**: use
`save_panel.py` on every edit and each panel's PDF + JSON are refreshed in the
same step.

The project-wide CSVs (`point_welds.csv`, `linear_welds.csv`, `area_welds.csv`)
are the one artifact `save_panel.py` does **not** touch — they aggregate every
panel. Rebuild them after adding, editing, or archiving a panel, or just re-sync
the whole directory at once:

```bash
python scripts/build_weld_csvs.py ./project                   # rebuild just the CSVs
python scripts/regenerate_artifacts.py ./project              # bulk: every PDF + weld positions + CSVs
python scripts/regenerate_artifacts.py ./project --revisions  # also render revision-history PDFs
python scripts/regenerate_artifacts.py ./project --prune      # drop orphaned artifacts (regenerable junk)
```

Do not leave a project with stale PDFs, CSVs, or position maps after an edit.

## Archive, don't delete

**Never delete a panel outright.** To retire a panel from active scope —
cancelled work, superseded design, completed teardown — **archive it**, which
moves its `.weldb` **and** all its derived files (`.pdf`, `_weld_positions.json`,
`_revisions.pdf`) **together** into an `archive/` folder, preserving the panel's
full revision history for audit:

```bash
python scripts/archive_panel.py N5.weldb                 # -> ./archive/ (whole set moves together)
python scripts/archive_panel.py N5.weldb N6.weldb        # archive several at once
```

Archiving is non-destructive and **batch-consistent**: if the same panel name was
archived before (e.g. `N9` redesigned a few times before its final shape, outside
the normal revision process, or removed then re-added to scope), each generation
is kept grouped under a shared suffix — `N9.*`, then `N9_1.*`, then `N9_2.*` —
never overwriting an earlier archived copy. After archiving, rebuild the project
CSVs so the retired panel drops out (`build_weld_csvs.py` or
`regenerate_artifacts.py`).

## Rendering and exporting individually

```bash
python scripts/render_pdf.py N5.weldb                 # -> N5.pdf (color by default)
python scripts/render_revision_history.py N5.weldb    # -> N5_revisions.pdf
python scripts/build_weld_csvs.py ./project           # point/linear/area CSVs
python scripts/weld_positions.py N5.weldb --canvas-w 1000 --canvas-h 800
```

Render PDFs **in color by default** (`render_pdf.py` and `regenerate_artifacts.py`
already do; pass `--no-color` only if the user wants black-on-white).
