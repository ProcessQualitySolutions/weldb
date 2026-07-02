"""Weld log utility for combining welds from multiple .weldb files."""

from __future__ import annotations

from pathlib import Path

from weldb.document import load
from weldb.welds import WELD_PREFIXES, get_point_welds
from weldb.exceptions import DuplicateWeldAcrossFilesError
from weldb.models import PointWeld

#: Separator joining the panel name to the weld ID in a project weld log
#: (e.g., panel ``N5`` + weld ``T250`` -> ``N5.T250``).
WELD_ID_SEPARATOR = "."


def prefix_weld_id(panel_name: str, weld_id: str) -> str:
    """Join a panel name to a weld ID using the project separator.

    The weld ID may still carry its grid type prefix (``*``/``_``/``@``); the
    single leading prefix character (and only that one) is stripped before
    joining. For example, ``("N5", "*T250")`` -> ``"N5.T250"``.
    """
    base = weld_id[1:] if weld_id[:1] in WELD_PREFIXES else weld_id
    return f"{panel_name}{WELD_ID_SEPARATOR}{base}"


def build_weld_log(directory: str | Path) -> list[PointWeld]:
    """Build a combined weld log from all .weldb files in a directory.

    For each file, extracts all point welds from the current map (deduplicating
    across views within each file). The panel name is prepended to each weld ID.

    For example, panel "N5" with weld "*T250" becomes weld_id "N5.T250".

    Raises DuplicateWeldAcrossFilesError if the same prefixed weld ID appears
    in more than one file.
    """
    directory = Path(directory)
    files = sorted(directory.glob("*.weldb"))

    all_welds: list[PointWeld] = []
    seen: dict[str, str] = {}  # prefixed weld_id -> source filename

    for filepath in files:
        doc = load(filepath)
        panel_name = doc["panel_name"]
        point_welds = get_point_welds(doc)

        for pw in point_welds:
            prefixed_id = prefix_weld_id(panel_name, pw.weld_id)

            if prefixed_id in seen:
                raise DuplicateWeldAcrossFilesError(
                    prefixed_id, [seen[prefixed_id], filepath.name]
                )

            seen[prefixed_id] = filepath.name
            all_welds.append(
                PointWeld(weld_id=prefixed_id, row=pw.row, col=pw.col)
            )

    return all_welds
