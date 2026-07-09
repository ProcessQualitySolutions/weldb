#!/usr/bin/env python3
"""Archive a panel — move its .weldb and ALL derived files together, don't delete.

Panels are never deleted outright (see ``references/project_spec.md``). To retire
a panel from active scope — cancelled work, superseded design, completed teardown
— this moves the whole set together into an ``archive/`` folder: the ``.weldb``
source **and** its ``.pdf``, ``_weld_positions.json``, and ``_revisions.pdf``. The
panel's full revision history is preserved for audit, and the active project (weld
log, CSVs, renders) stops counting it.

Usage:
    python scripts/archive_panel.py N5.weldb                 # -> ./archive/
    python scripts/archive_panel.py N5.weldb --archive-dir ./retired
    python scripts/archive_panel.py N5.weldb N6.weldb        # archive several

Archiving is non-destructive: a name already present in the archive is kept under
a ``_N`` suffix rather than overwriting an earlier archived copy. After archiving,
rebuild the project CSVs so the retired panel drops out
(``scripts/regenerate_artifacts.py ./project``).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from weldb import archive_panel  # noqa: E402
from weldb.exceptions import InvalidFileExtensionError  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("files", nargs="+", help="The .weldb panel file(s) to archive.")
    p.add_argument("--archive-dir", help="Destination folder (default: an 'archive/' dir beside each source).")
    p.add_argument("--no-revisions", dest="revisions", action="store_false",
                   help="Do not move the <stem>_revisions.pdf (leave it in place).")
    p.set_defaults(revisions=True)
    args = p.parse_args(argv)

    rc = 0
    for f in args.files:
        src = Path(f)
        if not src.is_file():
            print(f"Skipped {src}: not found.", file=sys.stderr)
            rc = 1
            continue
        try:
            moved = archive_panel(src, args.archive_dir, revisions=args.revisions)
        except InvalidFileExtensionError as exc:
            print(f"Skipped {src}: {exc}", file=sys.stderr)
            rc = 1
            continue
        dest_dir = moved[0].parent if moved else "(archive)"
        print(f"Archived {src.name}: moved {len(moved)} file(s) to {dest_dir}")
        for m in moved:
            print(f"  - {m.name}")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
