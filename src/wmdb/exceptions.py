"""WMDB exceptions."""


class WMDBError(Exception):
    """Base exception for all WMDB errors."""


class InvalidFileExtensionError(WMDBError):
    """Raised when a file does not have the expected extension for its standard."""

    def __init__(self, path: str, expected: str):
        self.path = path
        self.expected = expected
        super().__init__(
            f"Invalid file extension for '{path}' — expected '{expected}'"
        )


class DuplicatePointWeldError(WMDBError):
    """Raised when a point weld identifier appears more than once in a grid."""

    def __init__(self, weld_id: str, locations: list[tuple[int, int]]):
        self.weld_id = weld_id
        self.locations = locations
        super().__init__(
            f"Point weld '{weld_id}' is not unique — found at grid positions {locations}"
        )


class EmbeddedSpecialCharError(WMDBError):
    """Raised when *, _, or @ appears in a cell string but not as the first character."""

    def __init__(self, cell_value: str, row: int, col: int):
        self.cell_value = cell_value
        self.row = row
        self.col = col
        super().__init__(
            f"Cell ({row}, {col}) contains embedded special character: '{cell_value}'. "
            f"'*', '_', and '@' are only valid as the first character."
        )


class DuplicatePointWeldInViewError(WMDBError):
    """Raised when a point weld appears more than once in a single view's grid."""

    def __init__(self, weld_id: str, view_name: str, locations: list[tuple[int, int]]):
        self.weld_id = weld_id
        self.view_name = view_name
        self.locations = locations
        super().__init__(
            f"Point weld '{weld_id}' is not unique in view '{view_name}' "
            f"— found at grid positions {locations}"
        )


class ConflictingWeldIdError(WMDBError):
    """Raised when two welds of different types share the same base ID."""

    def __init__(self, base_id: str, weld_a: str, weld_b: str):
        self.base_id = base_id
        self.weld_a = weld_a
        self.weld_b = weld_b
        super().__init__(
            f"Conflicting weld IDs: '{weld_a}' and '{weld_b}' "
            f"share base ID '{base_id}' — these would collide in the weld log."
        )


class DuplicateWeldAcrossFilesError(WMDBError):
    """Raised when a point weld ID appears in more than one .weldb file in a project."""

    def __init__(self, weld_id: str, files: list[str]):
        self.weld_id = weld_id
        self.files = files
        super().__init__(
            f"Point weld '{weld_id}' found in multiple files: {files}"
        )
