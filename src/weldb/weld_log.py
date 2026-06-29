"""Weld log utility for combining welds from multiple .weldb files."""

from __future__ import annotations

from pathlib import Path

from weldb.document import load
from weldb.welds import get_point_welds
from weldb.exceptions import DuplicateWeldAcrossFilesError
from weldb.types import PointWeld


def build_weld_log(directory: str | Path) -> list[PointWeld]:
    """Build a combined weld log from all .weldb files in a directory.

    For each file, extracts all point welds from the current map (deduplicating
    across views within each file). The panel name is prepended to each weld ID.

    For example, panel "N5" with weld "*250T" becomes weld_id "N5-250T".

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
            label = pw.weld_id.lstrip("*")
            prefixed_id = f"{panel_name}-{label}"

            if prefixed_id in seen:
                raise DuplicateWeldAcrossFilesError(
                    prefixed_id, [seen[prefixed_id], filepath.name]
                )

            seen[prefixed_id] = filepath.name
            all_welds.append(
                PointWeld(weld_id=prefixed_id, row=pw.row, col=pw.col)
            )

    return all_welds
