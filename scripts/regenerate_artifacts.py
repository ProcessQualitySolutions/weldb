#!/usr/bin/env python3
"""Regenerate ALL derived artifacts for a weldb project directory.

Run this after every change — creating, modifying, or deleting a ``.weldb`` file
— so the derived artifacts never go stale. For each panel it:

  * re-renders the drawing PDF (``<panel>.pdf``, in color by default),
  * extracts the weld-position map (``<panel>_weld_positions.json``),

and then rebuilds the project-wide weld CSVs (``point_welds.csv``,
``linear_welds.csv``, ``area_welds.csv``) from every panel at once.

By default a panel is **skipped when it is already up to date** — its ``.pdf`` and
``_weld_positions.json`` both exist and are newer than the ``.weldb`` source — so
re-running over a project only re-renders what actually changed. Pass ``--force``
to re-render everything regardless.

The PDF and the weld-position map for each panel are produced in a **single layout
pass** (``weldb.render_panel_bundle``), not two.

Pass ``--revisions`` to also render each panel's full revision-history PDF. Pass
``--prune`` to delete orphaned artifacts — a ``.pdf`` / ``_revisions.pdf`` /
``_weld_positions.json`` whose ``.weldb`` no longer exists.

For a single panel prefer ``scripts/save_panel.py`` (save + render in one shot);
this script is for re-syncing a whole directory at once. To retire a panel, use
``scripts/archive_panel.py`` (move its files to ``archive/``) — never delete.

Usage:
    python scripts/regenerate_artifacts.py ./project
    python scripts/regenerate_artifacts.py ./project --force --revisions --prune

PDF and weld-position rendering need fpdf2 (``pip install fpdf2``); if it is
missing, those steps are skipped with a warning and the CSVs are still built.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import weldb  # noqa: E402

from build_weld_csvs import build_csvs  # noqa: E402  (sibling script)


def _up_to_date(source: Path, outputs: list[Path]) -> bool:
    """True if every output exists and is at least as new as ``source``."""
    src_mtime = source.stat().st_mtime
    return all(o.exists() and o.stat().st_mtime >= src_mtime for o in outputs)


def _prune(directory: Path, panels: set[str]) -> list[str]:
    """Remove derived files whose source .weldb is gone. Returns removed names."""
    removed: list[str] = []
    for pdf in directory.glob("*.pdf"):
        stem = pdf.stem[: -len("_revisions")] if pdf.stem.endswith("_revisions") else pdf.stem
        if stem not in panels:
            pdf.unlink()
            removed.append(pdf.name)
    for js in directory.glob("*_weld_positions.json"):
        stem = js.name[: -len("_weld_positions.json")]
        if stem not in panels:
            js.unlink()
            removed.append(js.name)
    return removed


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("directory", nargs="?", default=".", help="Project directory of .weldb files (default: cwd).")
    p.add_argument("--no-color", dest="color", action="store_false", help="Render PDFs black-on-white.")
    p.add_argument("--revisions", action="store_true", help="Also render each panel's revision-history PDF.")
    p.add_argument("--prune", action="store_true", help="Delete artifacts whose .weldb source no longer exists.")
    p.add_argument("--force", action="store_true",
                   help="Re-render every panel even if its artifacts are already up to date.")
    p.set_defaults(color=True)
    args = p.parse_args(argv)

    directory = Path(args.directory)
    if not directory.is_dir():
        raise SystemExit(f"Not a directory: {directory}")

    files = sorted(directory.glob("*.weldb"))
    panels = {f.stem for f in files}

    removed: list[str] = []
    if args.prune:
        removed = _prune(directory, panels)

    if not files:
        print(f"No .weldb files in {directory}." + (f" Pruned {len(removed)} orphan(s)." if removed else ""))
        return 0

    rendered = positions = revisions = skipped_fresh = 0
    pdf_errors: list[str] = []
    pdf_available = True
    for f in files:
        if not pdf_available:
            break
        paths = weldb.derived_artifact_paths(f, revisions=args.revisions)
        outputs = [paths["pdf"], paths["weld_positions"]]
        if args.revisions:
            outputs.append(paths["revisions_pdf"])
        if not args.force and _up_to_date(f, outputs):
            skipped_fresh += 1
            continue
        try:
            doc = weldb.load(f)
            # PDF + weld positions from a single layout pass.
            bundle = weldb.render_panel_bundle(doc, color=args.color)
            paths["pdf"].write_bytes(bundle["pdf_bytes"])
            paths["weld_positions"].write_text(
                json.dumps(bundle["positions"], indent=2), encoding="utf-8"
            )
            rendered += 1
            positions += 1
            if args.revisions:
                weldb.render_revision_history_pdf(f)
                revisions += 1
        except ImportError:
            pdf_available = False
            print("WARNING: fpdf2 not installed — skipping PDFs and weld positions. "
                  "Install it with `pip install fpdf2`.", file=sys.stderr)
        except Exception as exc:  # noqa: BLE001 — report per-file, keep going
            pdf_errors.append(f"{f.name}: {exc}")

    # Project-wide CSVs (always attempted; independent of fpdf2).
    texts, counts, skipped = build_csvs(files)
    for name, text in texts.items():
        (directory / name).write_text(text, encoding="utf-8")

    print(
        f"Regenerated in {directory}: {rendered} PDF(s), {positions} weld-position map(s)"
        + (f", {revisions} revision PDF(s)" if args.revisions else "")
        + (f", {skipped_fresh} already up to date" if skipped_fresh else "")
        + f"; CSVs — {counts['point']} point, {counts['linear']} linear, {counts['area']} area rows."
        + (f" Pruned {len(removed)} orphan(s)." if removed else "")
    )
    rc = 0
    if pdf_errors:
        print("PDF/position errors:", file=sys.stderr)
        for e in pdf_errors:
            print(f"  - {e}", file=sys.stderr)
        rc = 1
    if skipped:
        print("CSV skipped (fix and re-run):", file=sys.stderr)
        for s in skipped:
            print(f"  - {s}", file=sys.stderr)
        rc = 1
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
