"""weldb document loading and custom field access."""

from __future__ import annotations

import copy
import datetime
import re
from pathlib import Path
from typing import Any

import yaml

from weldb.exceptions import InvalidFileExtensionError, MissingRequiredFieldError

FILE_EXTENSION = ".weldb"
REQUIRED_FIELDS = {
    "panel_name", "tube_mtrl", "tube_od", "tube_wall", "units", "elevation", "maps"
}
# Known optional fields: interpreted by the library (so not treated as free
# "custom" fields) but not required.
OPTIONAL_FIELDS = {"elevation_at"}
RESERVED_FIELDS = REQUIRED_FIELDS | OPTIONAL_FIELDS | {"weld_overrides"}


def _validate_required_fields(doc: dict[str, Any]) -> None:
    """Ensure every field in :data:`REQUIRED_FIELDS` is present and non-empty.

    A weldb document is a top-level mapping; a non-dict document (e.g. an empty
    file that parses to ``None``) is rejected outright. ``elevation`` — and the
    other required fields — are free-form, but none may be missing, ``None``, or
    an empty/whitespace-only string. Raises :class:`MissingRequiredFieldError`
    naming the first offending field.
    """
    if not isinstance(doc, dict):
        raise MissingRequiredFieldError("panel_name")
    # Report in a stable, human-friendly order rather than set iteration order.
    ordered = [
        "panel_name", "tube_mtrl", "tube_od", "tube_wall", "units", "elevation", "maps",
    ]
    for field_name in ordered:
        value = doc.get(field_name)
        if value is None or (isinstance(value, str) and not value.strip()):
            raise MissingRequiredFieldError(field_name)


def _normalize_grids(doc: dict[str, Any]) -> None:
    """Coerce grid cells to strings and pad every row to a rectangular grid.

    Files written by hand or by other tools may carry unquoted numeric cells
    (``250`` instead of ``'250'``) or rows of unequal length. Left as-is these
    crash extraction (``'int' object is not subscriptable``) and rendering
    (``IndexError`` on ragged rows). Normalizing here — once, at load — gives
    every downstream consumer a uniform ``list[list[str]]`` grid. Mutates ``doc``
    in place.
    """
    for mp in doc.get("maps", []) or []:
        if not isinstance(mp, dict):
            continue
        for view in mp.get("views", []) or []:
            if not isinstance(view, dict):
                continue
            grid = view.get("grid")
            if not isinstance(grid, list):
                continue
            rows = [row if isinstance(row, list) else [] for row in grid]
            width = max((len(row) for row in rows), default=0)
            view["grid"] = [
                ["" if cell is None else str(cell) for cell in row]
                + [""] * (width - len(row))
                for row in rows
            ]


def load(path: str | Path) -> dict[str, Any]:
    """Load a .weldb YAML file and return it as a dict.

    Raises InvalidFileExtensionError if the file does not end with .weldb.
    Raises MissingRequiredFieldError if any required top-level field (see
    :data:`REQUIRED_FIELDS`) is missing or empty.

    Grid cells are coerced to strings and every row is padded to a rectangular
    grid, so downstream extraction and rendering always see a uniform
    ``list[list[str]]``.
    """
    path = Path(path)
    if path.suffix != FILE_EXTENSION:
        raise InvalidFileExtensionError(str(path), FILE_EXTENSION)
    with open(path, encoding="utf-8") as f:
        doc = yaml.safe_load(f)
    _validate_required_fields(doc)
    _normalize_grids(doc)
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
