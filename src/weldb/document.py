"""weldb document loading and custom field access."""

from __future__ import annotations

import copy
import datetime
import re
from pathlib import Path
from typing import Any

import yaml

from weldb.exceptions import InvalidFileExtensionError

FILE_EXTENSION = ".weldb"
REQUIRED_FIELDS = {"panel_name", "tube_mtrl", "tube_od", "tube_wall", "units", "maps"}
RESERVED_FIELDS = REQUIRED_FIELDS | {"weld_overrides"}


def load(path: str | Path) -> dict[str, Any]:
    """Load a .weldb YAML file and return it as a dict.

    Raises InvalidFileExtensionError if the file does not end with .weldb.
    """
    path = Path(path)
    if path.suffix != FILE_EXTENSION:
        raise InvalidFileExtensionError(str(path), FILE_EXTENSION)
    with open(path, encoding="utf-8") as f:
        doc = yaml.safe_load(f)
    return doc


def save(doc: dict[str, Any], path: str | Path) -> None:
    """Write a weldb document dict back to a .weldb YAML file.

    Raises InvalidFileExtensionError if the path does not end with .weldb.
    """
    path = Path(path)
    if path.suffix != FILE_EXTENSION:
        raise InvalidFileExtensionError(str(path), FILE_EXTENSION)
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(doc, f, default_flow_style=False, sort_keys=False, allow_unicode=True)


def _next_rev(prev_rev: Any) -> str:
    """Return the next revision identifier after ``prev_rev`` (e.g. ``R0`` -> ``R1``)."""
    if not prev_rev:
        return "R0"
    m = re.fullmatch(r"([A-Za-z]*)(\d+)", str(prev_rev))
    if m:
        return f"{m.group(1)}{int(m.group(2)) + 1}"
    return f"{prev_rev}-1"


def add_revision(
    doc: dict[str, Any],
    views: list[dict[str, Any]] | None = None,
    *,
    updated_by: str = "",
    comments: str | None = None,
    date: str | None = None,
    rev: str | None = None,
) -> dict[str, Any]:
    """Append a new revision (map) to a weldb document — append-only editing.

    Maps are never modified in place; this adds a new map object to the end of
    the ``maps`` array, which becomes the current (authoritative) revision.

    Defaults that revert to the previous revision when not supplied:

    - ``comments`` — the **description** of the revision. If not provided, it
      reverts to the previous revision's comments. Callers adding a revision
      should collect a note/description from the user; omitting it keeps the
      prior description rather than blanking it.
    - ``views`` — if not provided, the previous revision's views are carried
      forward (deep-copied), so a revision can record a note without changing
      the layout.
    - ``rev`` — auto-incremented from the previous revision (``R0`` -> ``R1``).
    - ``date`` — today's date (ISO 8601) if not provided.

    Returns the same ``doc`` (mutated in place).
    """
    maps = doc.setdefault("maps", [])
    prev = maps[-1] if maps else {}

    if comments is None:
        comments = prev.get("comments", "")
    if views is None:
        views = copy.deepcopy(prev.get("views", []))
    if rev is None:
        rev = _next_rev(prev.get("rev"))
    if date is None:
        date = datetime.date.today().isoformat()

    maps.append(
        {
            "rev": rev,
            "date": date,
            "updated_by": updated_by or prev.get("updated_by", ""),
            "comments": comments,
            "views": views,
        }
    )
    return doc


def custom_field_getter(doc: dict[str, Any], field_name: str) -> Any:
    """Get a custom (non-required) top-level field from a weldb document.

    Returns None if the field does not exist.
    """
    return doc.get(field_name)


def custom_field_setter(doc: dict[str, Any], field_name: str, value: Any) -> None:
    """Set a custom (non-required) top-level field on a weldb document.

    Raises ValueError if the field name collides with a required field.
    """
    if field_name in RESERVED_FIELDS:
        raise ValueError(
            f"'{field_name}' is a required or reserved field — use direct assignment, not custom_field_setter"
        )
    doc[field_name] = value
