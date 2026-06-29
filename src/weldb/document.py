"""weldb document loading and custom field access."""

from __future__ import annotations

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
    with open(path) as f:
        doc = yaml.safe_load(f)
    return doc


def save(doc: dict[str, Any], path: str | Path) -> None:
    """Write a weldb document dict back to a .weldb YAML file.

    Raises InvalidFileExtensionError if the path does not end with .weldb.
    """
    path = Path(path)
    if path.suffix != FILE_EXTENSION:
        raise InvalidFileExtensionError(str(path), FILE_EXTENSION)
    with open(path, "w") as f:
        yaml.dump(doc, f, default_flow_style=False, sort_keys=False)


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
