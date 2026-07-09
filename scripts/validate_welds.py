#!/usr/bin/env python3
"""Validate a project's weld-ID rules — uniqueness, panel naming, and grids.

Run this to check weld numbers **deterministically** instead of reasoning about
them by hand. It treats the given files as one project and checks the rules from
``references/drawing_spec.md`` / ``references/project_spec.md``:

  * each file's ``panel_name`` matches its filename (``N5.weldb`` -> ``N5``),
  * panel names are distinct across the project,
  * within each file: point welds are unique per view, no two weld types share a
    base ID (``*T5`` vs ``_T5``), and no cell has an embedded ``*``/``_``/``@``,
  * point-weld IDs are unique across the project **after panel-prefixing** — the
    same grid label on different panels (e.g. ``N1.T100`` and ``N9.T100``, two
    panels on the same tubes at different elevations) is NOT a conflict; only the
    same *prefixed* ID in two files is.

It reports EVERY problem it finds (not just the first) and exits non-zero if any
are found, so you can wire it into a check step. No rendering, so no fpdf2 needed.

Usage:
    python scripts/validate_welds.py ./project        # a directory of .weldb
    python scripts/validate_welds.py N5.weldb N6.weldb # explicit files
    python scripts/validate_welds.py                   # the current directory
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from weldb.validation import validate_files  # noqa: E402


def _collect_files(inputs: list[str]) -> list[Path]:
    """Expand files and directories into a sorted list of .weldb paths."""
    files: list[Path] = []
    for item in inputs:
        p = Path(item)
        if p.is_dir():
            files.extend(sorted(p.glob("*.weldb")))
        elif p.is_file():
            files.append(p)
        else:
            raise SystemExit(f"Not a file or directory: {p}")
    return files


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("inputs", nargs="*", help="One or more .weldb files, and/or directories of them (default: cwd).")
    args = p.parse_args(argv)

    files = _collect_files(args.inputs or ["."])
    if not files:
        print("No .weldb files found — nothing to validate.")
        return 0

    issues = validate_files(files)
    if not issues:
        print(f"OK — {len(files)} file(s) checked, weld IDs are valid and unique.")
        return 0

    print(f"Found {len(issues)} problem(s) across {len(files)} file(s):", file=sys.stderr)
    for issue in issues:
        print(f"  - [{issue.code}] {issue}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
