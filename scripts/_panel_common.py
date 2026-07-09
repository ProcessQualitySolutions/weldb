"""Shared helpers for the create_panel scripts (simplified & extended styles).

Both generators share everything except how a view's grid rows are assembled:
tube numbering (left-to-right, ``tube_start`` on the left, as seen from the hot
side), validation, view assembly, and file output. The two grid builders here
reproduce the documented styles — see
``examples/conventional_panel_simplified_membrane_style/`` and
``examples/conventional_panel_extended_membrane_style/``.
"""

from __future__ import annotations

import argparse
import datetime
import re
import sys
from pathlib import Path

# Bundled library — put src/ on the path so `import weldb` works with no install.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from build_weld_csvs import build_csvs  # noqa: E402  (sibling script)

from weldb import custom_field_setter, dumps, loads, save_panel  # noqa: E402

WALL_CODES = [
    "WLS", "ELS", "NTB", "STB", "NBN", "SBN", "ND", "SD",  # directional disambiguations
    "NE", "NW", "SE", "SW",  # corners
    "LS", "US", "TB", "BN",  # features
    "N", "S", "E", "W", "T", "F", "H", "D",  # single-letter walls
]
_WALL_RE = re.compile(r"^(" + "|".join(WALL_CODES) + r")(\d+)$")
VALID_UNITS = ["mm", "ft_in", "in", "dec_in", "dec_ft"]

# Number of interior body rows (the tall, mostly-empty middle of the panel).
DEFAULT_BODY_ROWS = 6


def column_letters(i: int) -> str:
    """Spreadsheet-style column label for a zero-based index (0->A, 25->Z, 26->AA)."""
    letters = ""
    i += 1
    while i > 0:
        i, rem = divmod(i - 1, 26)
        letters = chr(65 + rem) + letters
    return letters


def _membrane_labels(n_tubes: int) -> tuple[str, str, list[str], list[str]]:
    """Labels for a panel's membranes: (outer_left, outer_right, top_peanuts, bottom_peanuts).

    Outer membranes run the full height of the panel (they repeat down every row).
    The interior "peanut" closures between adjacent tube welds are distinct welds
    top vs. bottom, so they get their own label ranges (e.g. tops ``_B.._E``,
    bottoms ``_G.._J`` for a 5-tube panel).
    """
    m = n_tubes + 1  # membrane columns
    outer_left = f"_{column_letters(0)}"
    outer_right = f"_{column_letters(m - 1)}"
    top_peanuts = [f"_{column_letters(1 + i)}" for i in range(n_tubes - 1)]
    bottom_peanuts = [f"_{column_letters(m + i)}" for i in range(n_tubes - 1)]
    return outer_left, outer_right, top_peanuts, bottom_peanuts


def build_simplified_grid(tubes: list[int], body_rows: int = DEFAULT_BODY_ROWS) -> list[list[str]]:
    """Simplified membrane style: membranes only in the top/bottom weld rows."""
    n = len(tubes)
    ol, orr, top_p, bot_p = _membrane_labels(n)

    def weld_row(side: str, peanuts: list[str]) -> list[str]:
        row = [ol]
        for i, t in enumerate(tubes):
            row.append(f"*{side}{t}")
            if i < n - 1:
                row.append(peanuts[i])
        row.append(orr)
        return row

    def body_row() -> list[str]:
        row = [ol]
        for i, t in enumerate(tubes):
            row.append(str(t))
            if i < n - 1:
                row.append("")
        row.append(orr)
        return row

    grid = [weld_row("T", top_p)]
    grid.extend(body_row() for _ in range(body_rows))
    grid.append(weld_row("B", bot_p))
    return grid


def build_extended_grid(tubes: list[int], body_rows: int = DEFAULT_BODY_ROWS) -> list[list[str]]:
    """Extended membrane style: membranes drawn extending past the tube welds.

    Adds a numbers-only header/footer row and a membrane row above and below each
    weld row, so the membranes read as continuous bars running past the welds.
    """
    n = len(tubes)
    ol, orr, top_p, bot_p = _membrane_labels(n)

    def numbers_only() -> list[str]:
        row = [""]
        for i, t in enumerate(tubes):
            row.append(str(t))
            if i < n - 1:
                row.append("")
        row.append("")
        return row

    def membrane_row(peanuts: list[str]) -> list[str]:
        row = [ol]
        for i, t in enumerate(tubes):
            row.append(str(t))
            if i < n - 1:
                row.append(peanuts[i])
        row.append(orr)
        return row

    def weld_row(side: str, peanuts: list[str]) -> list[str]:
        row = [ol]
        for i, t in enumerate(tubes):
            row.append(f"*{side}{t}")
            if i < n - 1:
                row.append(peanuts[i])
        row.append(orr)
        return row

    def body_row() -> list[str]:
        row = [ol]
        for i, t in enumerate(tubes):
            row.append(str(t))
            if i < n - 1:
                row.append("")
        row.append(orr)
        return row

    grid = [numbers_only(), membrane_row(top_p), weld_row("T", top_p), membrane_row(top_p)]
    grid.extend(body_row() for _ in range(body_rows))
    grid.extend([membrane_row(bot_p), weld_row("B", bot_p), membrane_row(bot_p), numbers_only()])
    return grid


def _parse_custom_fields(pairs: list[str] | None) -> dict[str, str]:
    out: dict[str, str] = {}
    for pair in pairs or []:
        if "=" not in pair:
            raise SystemExit(f"--field expects key=value, got: {pair!r}")
        k, v = pair.split("=", 1)
        out[k.strip()] = v.strip()
    return out


def add_common_args(p: argparse.ArgumentParser) -> None:
    """Add the arguments shared by both create_panel scripts."""
    p.add_argument("panel_name", help="Panel identifier, e.g. N5, W3, LS2 (wall code + number).")
    p.add_argument("--mtrl", required=True, help="Tube material spec, e.g. 'SA-210 A1'.")
    p.add_argument("--od", type=float, required=True, help="Tube outside diameter.")
    p.add_argument("--wall", type=float, required=True, help="Tube wall thickness.")
    p.add_argument("--units", required=True, help=f"Unit system: {', '.join(VALID_UNITS)}.")
    p.add_argument("--elevation", required=True, help="Where the panel sits, e.g. '1850 in' or 'Scaffold L3'.")
    p.add_argument("--tube-start", type=int, required=True,
                   help="Leftmost tube number (as seen from the hot side; inclusive).")
    p.add_argument("--tube-end", type=int, required=True, help="Rightmost tube number (inclusive).")
    p.add_argument("--elevation-at", default="", help="Optional note for what elevation refers to (e.g. 'top').")
    p.add_argument("--updated-by", default="skill", help="Author of the R0 revision.")
    p.add_argument("--comments", default="Initial weld map layout", help="R0 revision comment.")
    p.add_argument("--field", action="append", metavar="KEY=VALUE",
                   help="Custom top-level field (repeatable), e.g. --field client='ACME Power'.")
    p.add_argument("--body-rows", type=int, default=DEFAULT_BODY_ROWS,
                   help=f"Interior body rows / panel height (default {DEFAULT_BODY_ROWS}).")
    p.add_argument("--cold-side", action="store_true",
                   help="Also add an empty cold_side view (normal panels are hot-side only).")
    p.add_argument("--view", action="append", metavar="NAME", default=None,
                   help="Add an extra empty view by name (repeatable).")
    p.add_argument("--out-dir", default=".", help="Directory to write <panel>.weldb into (default: cwd).")
    p.add_argument("--stdout", action="store_true", help="Print the YAML instead of writing a file.")
    p.add_argument("--no-color", dest="color", action="store_false", help="Render the PDF black-on-white.")
    p.set_defaults(color=True)


def build_doc(args: argparse.Namespace, grid_builder) -> dict:
    """Validate inputs and assemble the (round-trip-validated) document."""
    if not _WALL_RE.match(args.panel_name):
        raise SystemExit(
            f"Invalid panel name '{args.panel_name}'. Expected <wall_code><number> "
            f"(e.g. N5, W3, LS2). Valid wall codes: {', '.join(WALL_CODES)}"
        )
    if args.units not in VALID_UNITS:
        raise SystemExit(f"Invalid units '{args.units}'. One of: {', '.join(VALID_UNITS)}.")
    if not args.elevation.strip():
        raise SystemExit("elevation is required and must not be empty (e.g. '1850 in').")
    if args.tube_start > args.tube_end:
        raise SystemExit(f"tube-start ({args.tube_start}) must be <= tube-end ({args.tube_end}).")
    if args.body_rows < 1:
        raise SystemExit("--body-rows must be at least 1.")

    doc: dict = {
        "panel_name": args.panel_name,
        "tube_mtrl": args.mtrl,
        "tube_od": args.od,
        "tube_wall": args.wall,
        "units": args.units,
        "elevation": args.elevation,
    }
    if args.elevation_at.strip():
        doc["elevation_at"] = args.elevation_at
    for k, v in _parse_custom_fields(args.field).items():
        try:
            custom_field_setter(doc, k, v)
        except ValueError as exc:
            raise SystemExit(f"Invalid custom field '{k}': {exc}")

    tubes = list(range(args.tube_start, args.tube_end + 1))
    hot_grid = grid_builder(tubes, args.body_rows)
    rows, cols = len(hot_grid), len(hot_grid[0])
    views = [{"name": "hot_side", "grid": hot_grid}]
    if args.cold_side:
        views.append({"name": "cold_side", "grid": [[""] * cols for _ in range(rows)]})
    for name in args.view or []:
        views.append({"name": name, "grid": [[""] * cols for _ in range(rows)]})

    doc["maps"] = [
        {
            "rev": "R0",
            "date": datetime.date.today().isoformat(),
            "updated_by": args.updated_by,
            "comments": args.comments,
            "views": views,
        }
    ]

    content = dumps(doc)
    loads(content)  # raises if the library would reject what we generated
    return doc


def write_result(args: argparse.Namespace, doc: dict, style_label: str) -> int:
    """Write (or print) the assembled doc, render its artifacts, and report."""
    if args.stdout:
        sys.stdout.write(dumps(doc))
        return 0

    n_tubes = args.tube_end - args.tube_start + 1
    view_names = ", ".join(v["name"] for v in doc["maps"][0]["views"])
    out_dir = Path(args.out_dir)
    out = out_dir / f"{args.panel_name}.weldb"
    out_dir.mkdir(parents=True, exist_ok=True)

    # Always render on save: write the .weldb and render its PDF together, so a
    # new scaffold never lands without its drawing. Rendering is not optional.
    try:
        written = save_panel(doc, out, color=args.color)
    except ImportError as exc:
        raise SystemExit(
            f"Wrote {out} (validated) but could not render — needs fpdf2: {exc}. "
            "Install it (`pip install fpdf2`) or build an HTML artifact "
            "(references/html_artifact_editor.md)."
        )

    # Rebuild the project weld CSVs for the output directory so the new panel's
    # welds and their coordinates appear immediately.
    files = sorted(out_dir.glob("*.weldb"))
    texts, _counts, _skipped = build_csvs(files)
    for csv_name, text in texts.items():
        (out_dir / csv_name).write_text(text, encoding="utf-8")

    artifacts = ", ".join(str(p) for role, p in written.items() if role != "weldb")
    print(
        f"Wrote {out} — {style_label}, tubes {args.tube_start}-{args.tube_end} "
        f"({n_tubes} tubes), {n_tubes * 2} point welds, {n_tubes * 2} membrane welds, "
        f"views: {view_names}."
        + f"\nRendered: {artifacts}."
        + f"\nRebuilt weld CSVs in {out_dir}."
        + "\nThis is a scaffold — edit the YAML to match the real panel (see "
        "references/drawing_spec.md and examples/), then re-save it with "
        "scripts/save_panel.py to re-render its artifacts."
    )
    return 0
