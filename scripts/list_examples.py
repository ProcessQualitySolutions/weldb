#!/usr/bin/env python3
"""Browse the bundled worked-example .weldb catalog.

With no argument it lists each arrangement folder with a one-line description;
with ``--example NAME`` it lists the files in that folder. To read an example,
just open the file
directly — they are plain bundled files under ``examples/`` (no tool needed):

    python scripts/list_examples.py                 # list arrangements
    python scripts/list_examples.py -e adjacent_panels
    cat examples/adjacent_panels/N5.weldb           # read one directly
"""

from __future__ import annotations

import argparse
from pathlib import Path

EXAMPLES_DIR = Path(__file__).resolve().parent.parent / "examples"


def _first_comment_line(path: Path) -> str:
    """First leading ``#`` comment line of a file (without the '#'), or ''."""
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                s = line.strip()
                if not s:
                    continue
                return s.lstrip("#").strip() if s.startswith("#") else ""
    except OSError:
        pass
    return ""


def _weldb_files(directory: Path) -> list[Path]:
    return sorted(directory.glob("*.weldb"))


def list_all() -> str:
    if not EXAMPLES_DIR.is_dir():
        return f"No examples directory found at {EXAMPLES_DIR}"
    dirs = sorted(p for p in EXAMPLES_DIR.iterdir() if p.is_dir())
    if not dirs:
        return f"No example folders found in {EXAMPLES_DIR}"
    lines = ["Example catalog (examples/):", ""]
    for d in dirs:
        files = _weldb_files(d)
        desc = _first_comment_line(files[0]) if files else ""
        header = f"  {d.name}/ ({len(files)} file{'s' if len(files) != 1 else ''})"
        lines.append(f"{header}  {desc}".rstrip())
    return "\n".join(lines)


def list_one(example: str) -> str:
    folder = (EXAMPLES_DIR / example).resolve()
    base = EXAMPLES_DIR.resolve()
    # Guard against path traversal, then require it to be a real subfolder.
    if base not in folder.parents or not folder.is_dir():
        names = ", ".join(p.name for p in sorted(EXAMPLES_DIR.iterdir()) if p.is_dir())
        return f"Example '{example}' not found. Available: {names or '(none)'}"
    files = _weldb_files(folder)
    if not files:
        return f"Example '{example}' has no .weldb files."
    lines = [f"Files in examples/{example}/:", ""]
    for f in files:
        lines.append(f"  {f.name:20s} {_first_comment_line(f)}".rstrip())
    lines.append("")
    lines.append("Read one directly, e.g.:  cat examples/" + example + "/" + files[0].name)
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("-e", "--example", help="List the files in one arrangement folder.")
    args = p.parse_args(argv)
    print(list_one(args.example) if args.example else list_all())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
