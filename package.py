#!/usr/bin/env python3
"""Package this project into a distributable ``weldb.skill`` file.

A ``.skill`` file is just a zip archive of the skill directory. This bundles the
whole project — SKILL.md, the scripts, the bundled ``weldb`` library under
``src/``, the ``examples/`` catalog, the ``references/`` docs, and the tests — so
the skill is fully self-contained and needs no pip install or PyPI access.

Deliberately EXCLUDED from the archive:
  * ``weldb_visual_editor.py``     — the desktop Tkinter app (won't run headless;
                                     kept in the repo for advanced/local users).
  * ``examples/render_all_examples.py`` — a local convenience render script.
  * ``package.py``                 — this packer itself.
  * VCS/build/cache/editor/OS junk and generated artifacts (PDFs, weld CSVs,
    ``*_weld_positions.json``, ``__pycache__``, ``*.egg-info``, ``.venv`` …).

The archive lays the files under a top-level ``weldb/`` folder, so unzipping it
yields a ready-to-load ``weldb/`` skill directory with ``SKILL.md`` at its root.

Usage:
    python package.py                 # -> ./weldb.skill
    python package.py -o dist/weldb.skill
"""

from __future__ import annotations

import argparse
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
SKILL_NAME = "weldb"                 # top-level folder inside the archive
DEFAULT_OUTPUT = REPO_ROOT / "weldb.skill"

# Files excluded by their path relative to the repo root (posix form).
EXCLUDE_RELPATHS = {
    "weldb_visual_editor.py",
    "examples/render_all_examples.py",
    "package.py",
}
# Directory names excluded wherever they appear in the tree.
EXCLUDE_DIRS = {
    ".git", ".venv", "venv", "__pycache__", ".pytest_cache", ".ruff_cache",
    ".idea", ".vscode", "dist", "build", "node_modules", ".claude",
}
# File suffixes that are never shipped (generated / compiled).
EXCLUDE_SUFFIXES = {".pyc", ".pyo", ".pdf", ".skill"}
# Exact generated-artifact basenames that may litter the root during dev.
EXCLUDE_BASENAMES = {
    ".DS_Store", "Thumbs.db", "desktop.ini",
    "point_welds.csv", "linear_welds.csv", "area_welds.csv",
}


def _excluded(rel: Path) -> bool:
    """True if the repo-relative path should be left out of the archive."""
    if rel.as_posix() in EXCLUDE_RELPATHS:
        return True
    if any(part in EXCLUDE_DIRS or part.endswith(".egg-info") for part in rel.parts):
        return True
    if rel.suffix in EXCLUDE_SUFFIXES:
        return True
    name = rel.name
    if name in EXCLUDE_BASENAMES:
        return True
    if name.startswith("__temp") or name.endswith("_weld_positions.json"):
        return True
    return False


def collect_files(root: Path, output: Path) -> list[Path]:
    """Repo-relative paths to include, sorted for a deterministic archive."""
    files: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if path.resolve() == output.resolve():  # never zip the output into itself
            continue
        rel = path.relative_to(root)
        if _excluded(rel):
            continue
        files.append(rel)
    return sorted(files, key=lambda p: p.as_posix())


def build(output: Path) -> None:
    if "SKILL.md" not in {p.name for p in REPO_ROOT.glob("SKILL.md")}:
        raise SystemExit("SKILL.md not found at repo root — is this the skill directory?")

    rels = collect_files(REPO_ROOT, output)
    output.parent.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as zf:
        for rel in rels:
            arcname = f"{SKILL_NAME}/{rel.as_posix()}"
            zf.write(REPO_ROOT / rel, arcname)

    size_kb = output.stat().st_size / 1024
    print(f"Wrote {output}  ({len(rels)} files, {size_kb:.1f} KiB)")
    print(f"  archive root: {SKILL_NAME}/")
    top = sorted({rel.parts[0] for rel in rels})
    print("  includes:    " + ", ".join(top))


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("-o", "--output", type=Path, default=DEFAULT_OUTPUT,
                   help="Output .skill path (default: ./weldb.skill).")
    args = p.parse_args(argv)
    build(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
