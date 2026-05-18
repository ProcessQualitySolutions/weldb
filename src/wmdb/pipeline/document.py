"""WMDB Pipeline document loading — placeholder."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from wmdb.exceptions import InvalidFileExtensionError

FILE_EXTENSION = ".weldp"


def load(path: str | Path) -> dict[str, Any]:
    """Load a .weldp YAML file and return it as a dict.

    Raises InvalidFileExtensionError if the file does not end with .weldp.
    """
    path = Path(path)
    if path.suffix != FILE_EXTENSION:
        raise InvalidFileExtensionError(str(path), FILE_EXTENSION)
    with open(path) as f:
        doc = yaml.safe_load(f)
    return doc


def save(doc: dict[str, Any], path: str | Path) -> None:
    """Write a WMDB Pipeline document dict back to a .weldp YAML file.

    Raises InvalidFileExtensionError if the path does not end with .weldp.
    """
    path = Path(path)
    if path.suffix != FILE_EXTENSION:
        raise InvalidFileExtensionError(str(path), FILE_EXTENSION)
    with open(path, "w") as f:
        yaml.dump(doc, f, default_flow_style=False, sort_keys=False)
