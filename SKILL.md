---
name: weldb
description: >-
  Create, edit, render, and export boiler-repair weld maps stored as .weldb YAML
  files. Use when the user works with .weldb files or boiler panel weld maps:
  generating a panel scaffold, laying out tubes/membranes/welds, producing an
  engineering-drawing PDF, exporting weld CSVs (which include each weld's
  on-drawing coordinates), or building an interactive editor for a weld map.
  Bundles the weldb Python library, so no pip install or network access is
  required.
license: MIT
---

# weldb — Boiler Weld Map Skill

<sub>Developed by the [qcdatabase.ai](https://qcdatabase.ai) team.</sub>

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

Run these with the bundled library — no install needed (scripts that render
additionally need `fpdf2`; `pip install fpdf2` if it's missing).

| Script | Does |
|--------|------|
| `scripts/create_panel_extended_membrane.py` | Generate a conventional panel **scaffold** in the **extended** membrane style, **and render it** (see below). **Prefer this.** |
| `scripts/create_panel.py` | Same, but the **simplified** membrane style. Use only if the user asks for it. |
| `scripts/create_panels.py` | **Create + render MANY panels from one JSON spec, in one process.** Use for stacked/adjacent/overlapping sets (see **Creating multiple panels**). |
| `scripts/save_panel.py` | **Save a panel and regenerate ALL its artifacts in one shot** — validate + write the `.weldb`, render its PDF, and rebuild the project weld CSVs. **Use this after every edit** (see **Always render on save**). |
| `scripts/archive_panel.py` | Retire a panel: **move** its `.weldb` + `.pdf` (+ `_revisions.pdf`) together into `archive/` (never delete — see **Archive, don't delete**). |
| `scripts/render_pdf.py` | Render a panel to a single-sheet engineering-drawing PDF only (**color by default**). |
| `scripts/render_revision_history.py` | Render the full revision history to a standalone PDF. |
| `scripts/build_weld_csvs.py` | Point/linear/area weld CSVs from files/dirs — each row carries the weld's on-drawing coordinates (`x0, y0, x1, y1`, leftmost view) plus resolved properties. |
| `scripts/query_welds.py` | **Pull one panel's welds out of the CSVs by name** — deterministic weld counts and rows for a single panel (e.g. "how many welds are on N1?") or to hand a drawing's welds to another system. Reads the CSVs only; no `fpdf2` needed. |
| `scripts/weld_positions_to_canvas.py` | **Convert a panel's PDF weld positions (mm) to HTML5-canvas pixels** — pass panel name + canvas width/height; scales by width, validates nothing lands outside the canvas, emits JSON keyed by project weld ID. For POSTing to a canvas-based weld tracking system. Needs `fpdf2`. |
| `scripts/validate_welds.py` | **Check weld-ID uniqueness + naming across a project deterministically** (see **Checking weld-ID uniqueness**). Run this instead of reasoning about weld numbers by hand. No `fpdf2` needed. |
| `scripts/regenerate_artifacts.py` | Bulk re-sync a whole project: re-render each changed panel's PDF and rebuild the CSVs. Skips panels already up to date (`--force` to override). |
| `scripts/list_examples.py` | Browse the bundled example catalog. |

Every script has `--help`. **There is no way to save a panel without rendering its
PDF and rebuilding the CSVs** — that coupling is deliberate (see **Always render
on save**), so don't look for a "just write the YAML" flag.

## Always render on save

**A `.weldb` file is never saved without its derived artifacts, and there is no
opt-out.** The `.weldb` YAML is the source of truth; its PDF (`<panel>.pdf`) and
the project weld CSVs are derived, and they must never lag behind it. So **every
create or update renders the PDF and rebuilds the CSVs in the same step** — one
command, one round trip, no stale artifacts:

```bash
# After editing a .weldb (with the Write/Edit tools or by hand), save it:
python scripts/save_panel.py N5.weldb              # -> N5.weldb (validated) + N5.pdf + rebuilt weld CSVs
python scripts/save_panel.py N5.weldb --revisions  # also N5_revisions.pdf

# One-shot create: pipe YAML in and it is written AND rendered together:
python scripts/save_panel.py N5.weldb --stdin < draft.yaml
```

`save_panel.py` also **round-trip-validates** the YAML (so a hand-tweak can't
corrupt it), replacing the separate validation step. The `create_panel*` scripts
render and rebuild the CSVs on save too, so a fresh scaffold already has its PDF
and shows up in the CSVs. Prefer `save_panel.py` for a single panel; use
`regenerate_artifacts.py` only to re-sync a whole directory in bulk. (Rendering
needs `fpdf2`; if it is missing the `.weldb` is written but the command fails so
the stale state is obvious — install it with `pip install fpdf2`, or build an HTML
artifact instead.)

**Weld coordinates live in the CSVs, not a JSON file.** Each CSV row carries the
weld's on-drawing bounding box (`x0, y0, x1, y1` — millimetres, top-left origin).
These four numbers are a **rectangle**, not two separate points: `(x0, y0)` is the
top-left corner and `(x1, y1)` the bottom-right corner of the weld's box on the
drawing (`x0 ≤ x1`, `y0 ≤ y1`, y increasing downward). The coordinates are
computed by the renderer, so treat them as that box — to get a weld's centre,
average the corners (`((x0+x1)/2, (y0+y1)/2)`). A weld that appears in several
views is mapped in the **leftmost view** only. The old
`<panel>_weld_positions.json` artifact no longer exists.

## Creating a panel

1. Read `references/drawing_spec.md` and the closest `examples/` arrangement.
2. Determine the panel name from `references/panel_naming_convention.md` (wall
   code + next sequential number — read the user's existing `.weldb` files to
   continue the sequence). Confirm material, OD, wall, units, elevation, and the
   tube range with the user. If the user gives elevation as a **range** (e.g.
   `1850–1878 in`), record that whole range as `elevation` and set
   `--elevation-at range` — do **not** collapse it to a single `top`/`bottom`
   value.
3. Scaffold it. **Use the extended membrane style by default** — run
   `create_panel_extended_membrane.py`. Only use `create_panel.py` (simplified
   style) if the user specifically asks for the simplified/basic look.
   ```bash
   python scripts/create_panel_extended_membrane.py N5 --mtrl "SA-210 A1" \
       --od 2.0 --wall 0.15 --units in --elevation "1850 in" \
       --tube-start 250 --tube-end 254
   ```
   The scaffold command **renders on save**, so `N5.weldb` and `N5.pdf` appear
   together and the panel's welds show up in the project CSVs.
4. **The scaffold is the conventional layout only — not a finished panel.** Edit
   the generated YAML to match what the user actually described: add ports,
   clips, cladding/area welds, dutchman repairs, weld-length overrides,
   dropped/offset tubes, extra views, or custom fields. Then **save+render it in
   one shot** — this re-validates the YAML (a hand-tweak can't corrupt it) and
   refreshes the PDF and the weld CSVs together:
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
**one** physical weld and must be recorded on **one** panel only, so it gets one
project weld ID. Never duplicate a shared boundary weld onto both panels. Study
the `adjacent_panels`, `stacked_panels`, and `overlapping_panels` examples before
laying out a set.

> **Weld-ID uniqueness — read this before you archive or rename anything.** Weld
> IDs are unique **after they are prefixed with the panel name**. Every grid label
> is prefixed with its panel on export: grid `*T100` on panel `N5` becomes the
> project ID `N5.T100`. So the **same grid label on different panels never
> collides** — two panels covering the same tubes at different elevations (e.g.
> `N1` and `N9`, each with tubes `T100`–`T103`) are completely valid; they become
> `N1.T100…` and `N9.T100…`. **Do not archive or rename a panel just because
> another panel already uses the same tube/weld labels** — that is not a conflict.
> A real duplicate is the *same prefixed ID* on two panels, which only happens
> when the same physical weld is recorded twice (see `references/project_spec.md`).
> **Don't infer any of this — run `scripts/validate_welds.py` to check it** (see
> **Checking weld-ID uniqueness**).

After scaffolding a set, remember to [present the PDFs](#present-the-pdf-to-the-user):
for a multi-panel request, list the panels with a link/path to each PDF rather
than dumping them all inline.

## Checking weld-ID uniqueness

Weld-ID uniqueness is a **rule with a checker — do not reason about it by hand.**
Whenever you're unsure whether a weld number "already exists," or before you
archive/rename a panel over a suspected clash, run:

```bash
python scripts/validate_welds.py ./project        # a whole project directory
python scripts/validate_welds.py N1.weldb N9.weldb # specific files, checked as a set
```

It checks, across the given files at once, every weld-ID rule in the spec:
`panel_name` matches the filename, panel names are distinct, each file's grid is
valid (point welds unique per view, no `*T5`/`_T5` base-ID clash, no embedded
`*`/`_`/`@`), and **point-weld IDs are unique across the project once
panel-prefixed**. It prints every problem it finds and exits non-zero if any
exist; a clean project prints `OK`. No `fpdf2` needed.

Because the project ID is panel-prefixed, `N1` and `N9` on the same tubes at
different elevations validate cleanly — the checker will tell you so. A genuine
duplicate only appears when two files declare the same `panel_name` (or the same
physical weld is recorded twice). In library code: `weldb.validate_project(dir)`
or `weldb.validate_files([...])` returns the same `ValidationIssue` list.

## Prefer one process over many

Every script call pays Python + `fpdf2` startup, and every call is a round trip.
So collapse work into as few invocations as possible: use `save_panel.py` (save,
render, and rebuild the CSVs together) instead of chaining `render_pdf.py` +
`build_weld_csvs.py`; `create_panels.py` for a set instead of N single creates;
and `regenerate_artifacts.py` for a whole-directory re-sync. (In library code,
`weldb.render_pdf_bytes(doc)` renders the PDF, and `weldb.first_view_weld_boxes(doc)`
computes the leftmost-view weld coordinates the CSVs carry.)

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

The `.weldb` YAML is always the source of truth; PDFs and the weld CSVs are
**derived artifacts** that must never lag behind it. The primary way to keep them
in sync is **[always render on save](#always-render-on-save)**: use
`save_panel.py` on every edit and the panel's PDF **and** the project CSVs are
refreshed in the same step. (The `create_panel*` scaffolds do this too.)

You normally don't need to rebuild anything by hand. When you do — e.g. after
**archiving** a panel (so the retired panel drops out of the CSVs), or to re-sync
a directory that was edited outside the save scripts — use:

```bash
python scripts/build_weld_csvs.py ./project                   # rebuild just the CSVs (with coordinates)
python scripts/regenerate_artifacts.py ./project              # bulk: every changed PDF + rebuilt CSVs
python scripts/regenerate_artifacts.py ./project --revisions  # also render revision-history PDFs
python scripts/regenerate_artifacts.py ./project --prune      # drop orphaned artifacts (and legacy *_weld_positions.json)
```

Do not leave a project with stale PDFs or CSVs after an edit.

## Archive, don't delete

**Never delete a panel outright.** To retire a panel from active scope —
cancelled work, superseded design, completed teardown — **archive it**, which
moves its `.weldb` **and** all its derived files (`.pdf`, `_revisions.pdf`)
**together** into an `archive/` folder, preserving the panel's full revision
history for audit:

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
python scripts/build_weld_csvs.py ./project           # point/linear/area CSVs (with x0..y1 coordinates)
python scripts/query_welds.py N1 --csv-dir ./project  # pull N1's welds from those CSVs (counts, or --format json/csv)
python scripts/weld_positions_to_canvas.py N1 --width 1200 --height 928  # mm weld boxes -> HTML5-canvas pixels
python scripts/validate_welds.py ./project            # check weld-ID uniqueness + naming
```

To answer a question about a single panel's welds ("how many welds are on N1?")
or to export one drawing's welds to another system, prefer
`query_welds.py` over re-reading the YAML — it filters the already-built CSVs by
panel name in one step (summary counts by default; `--format json`/`csv` for the
full rows). Build the CSVs first if they are missing or stale.

**Pushing welds to a canvas-based weld tracking system.** When the target system
draws the panel on an HTML5 canvas, use `weld_positions_to_canvas.py` to convert
the drawing's weld boxes to that canvas's pixels in one step — pass the panel name
and the canvas `--width`/`--height` you got from the tracking program's uploaded
drawing. The rendered PDF page and a canvas share the **same** orientation
(top-left origin, x right, y **down**), so the conversion is a pure width-based
scale with **no vertical flip** — do this programmatically with the tool rather
than reasoning coordinates out by hand. Scaling is keyed to the width; the height
is validated so no weld lands off-canvas (the tool fails and reports the minimum
height if the canvas is too short for the drawing's aspect ratio). Output is JSON
keyed by project weld ID (`N1.T100`), ready to POST.

**Example tracker — qcdatabase.ai (via its MCP server).** [qcdatabase.ai](https://qcdatabase.ai)
is a canvas-based weld/QC tracker that places each weld as a **map item** pinned to
an uploaded drawing, using **exactly this canvas coordinate system** (pixels of the
rendered drawing image, top-left origin, y down). So `weld_positions_to_canvas.py`
output drops straight in. **If the `qcdatabase` MCP server is installed** (its
`mcp__qcdatabase__*` tools are available), that's the signal to push the panel there
— render the panel's PDF, upload it, and place its welds in one flow:

1. **Upload the panel PDF.** `mcp__qcdatabase__upload_drawing` (or, when it belongs
   to a package, `mcp__qcdatabase__upload_drawing_to_package`) with the panel's
   rendered `<panel>.pdf`. Confirm the package/new-revision questions those tools ask.
2. **Read the canvas size.** `mcp__qcdatabase__get_drawing` returns the sheet's pixel
   `width`/`height` — the exact coordinate space the map items use. (Right after
   upload these may be `null` until the server finishes rendering; call again until
   they appear.) **Never guess the canvas size.**
3. **Convert with that width/height.** Run
   `python scripts/weld_positions_to_canvas.py <panel> --width <W> --height <H>`
   using the pixels from step 2. No flip or translation is needed — the conversion is
   a pure width scale — and the tool validates that every weld lands on-canvas.
4. **Get the Weld schema id.** `mcp__qcdatabase__list_map_item_schemas` → the `Weld`
   schema's id.
5. **Place the welds.** Feed the tool's JSON to `mcp__qcdatabase__bulk_create_map_items`
   (one batch per drawing): each weld's project ID (`N1.T100`) is the map item
   `label`. How the canvas pixels map depends on the weld's display style (see below).
   This adds all the sheet's weld pins in one atomic request.

**Flag vs. rectangular welds — prefer rectangular for weldb.** qcdatabase.ai renders a
map item in one of two styles, controlled by the boolean `is_rect` field on the Weld
schema/map-item settings:

- **Flag style** (`is_rect` off) — a single-point pin. Map the weld's box **centre**:
  `x_position`/`y_position` = the tool's `cx`/`cy`.
- **Rectangular style** (`is_rect` on) — a two-point box, defined exactly the way weldb
  defines welds (top-left + lower-right corners). Map both corners:
  `x_position`/`y_position` = `x0`/`y0` and `x_position_2`/`y_position_2` = `x1`/`y1`.

**Every weldb boiler weld type is rectangular in its visual display**, so the
rectangular style is the faithful representation and is the **desired setting when
using this skill/system**. So: **if rectangular welds are turned on**, place the two
corners (`x0,y0` → `x1,y1`). **If they are not**, recommend to the user that they
enable rectangular welds (`is_rect`) for all weldb boiler weld types in their
qcdatabase.ai map-item settings — until they do, fall back to flag-style centre pins
(`cx`/`cy`), but note the boxes will render as single points rather than the weld
rectangles.

This is the intended path when a user with the qcdatabase MCP server asks to
"upload"/"push"/"sync" a panel or its welds to their tracker: **convert with the tool,
then upload the drawing and its welds** — don't hand-place pins or reason coordinates
out by hand.

Render PDFs **in color by default** (`render_pdf.py` and `regenerate_artifacts.py`
already do; pass `--no-color` only if the user wants black-on-white).
