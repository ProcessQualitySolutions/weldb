"""Project-wide validation of the weld-ID rules from the spec.

This is the deterministic check for the naming and **uniqueness** rules in
``references/drawing_spec.md`` and ``references/project_spec.md`` — run it instead
of reasoning about weld numbers by hand. It reports **every** problem it finds in
one pass (it does not stop at the first), so a whole project can be validated at
once.

Rules checked:

* **panel_name matches the filename** — ``N5.weldb`` must contain
  ``panel_name: N5`` (``drawing_spec.md``, File Convention).
* **panel names are distinct** across the project — two files must not declare the
  same ``panel_name``.
* **within-file weld-grid rules** — a point weld is unique within a view, no two
  weld types share a base ID (e.g. ``*T5`` vs ``_T5``), and no cell has an embedded
  ``*``/``_``/``@`` (all raised by :func:`weldb.get_point_welds`).
* **point-weld IDs are unique across the project once panel-prefixed** — this is
  the rule the naming convention exists to satisfy. The same grid label on
  different panels is **fine** (``N1.T100`` and ``N9.T100`` do not collide); only
  the *same prefixed ID* appearing in two files is a duplicate. In practice that
  can only happen when panel names collide, so distinct panel names plus clean
  per-file grids already guarantee project-wide uniqueness — there is nothing to
  infer.

No rendering is involved, so this needs neither ``fpdf2`` nor a layout pass.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from weldb.document import load
from weldb.exceptions import WeldbError
from weldb.weld_log import prefix_weld_id
from weldb.welds import get_point_welds


@dataclass(frozen=True)
class ValidationIssue:
    """One problem found by :func:`validate_files`.

    ``code`` is a stable machine-readable slug (``load_error``,
    ``panel_name_mismatch``, ``duplicate_panel_name``, ``invalid_weld_grid``,
    ``duplicate_point_weld``); ``file`` is the offending file's name; ``message``
    is a human-readable explanation.
    """

    file: str
    code: str
    message: str

    def __str__(self) -> str:
        return f"{self.file}: {self.message}"


def validate_files(files: list[str | Path]) -> list[ValidationIssue]:
    """Validate the weld-ID rules across a set of ``.weldb`` files.

    Treats ``files`` as one project: point-weld uniqueness is checked across the
    whole set. Returns a list of :class:`ValidationIssue` — empty when everything
    is valid. Files are processed in the given order; a file that fails to load is
    reported and skipped without aborting the rest.
    """
    issues: list[ValidationIssue] = []
    seen_points: dict[str, str] = {}  # prefixed point-weld ID -> first file
    seen_panels: dict[str, str] = {}  # panel_name -> first file

    for raw in files:
        path = Path(raw)
        name = path.name
        try:
            doc = load(path)
        except Exception as exc:  # noqa: BLE001 — report and continue, never abort
            issues.append(ValidationIssue(name, "load_error", f"failed to load: {exc}"))
            continue

        panel = doc.get("panel_name")
        if panel != path.stem:
            issues.append(ValidationIssue(
                name, "panel_name_mismatch",
                f"panel_name '{panel}' does not match filename stem '{path.stem}'",
            ))
        if panel in seen_panels:
            issues.append(ValidationIssue(
                name, "duplicate_panel_name",
                f"panel_name '{panel}' is also declared by {seen_panels[panel]}",
            ))
        else:
            seen_panels[panel] = name

        # get_point_welds enforces the within-file rules (unique-in-view,
        # conflicting base IDs, embedded special chars) as it extracts.
        try:
            point_welds = get_point_welds(doc)
        except WeldbError as exc:
            issues.append(ValidationIssue(name, "invalid_weld_grid", str(exc)))
            continue

        for pw in point_welds:
            prefixed = prefix_weld_id(panel, pw.weld_id)
            if prefixed in seen_points:
                issues.append(ValidationIssue(
                    name, "duplicate_point_weld",
                    f"point weld '{prefixed}' is also recorded in {seen_points[prefixed]}",
                ))
            else:
                seen_points[prefixed] = name

    return issues


def validate_project(directory: str | Path) -> list[ValidationIssue]:
    """Validate every ``.weldb`` file in a project directory (see :func:`validate_files`)."""
    directory = Path(directory)
    return validate_files(sorted(directory.glob("*.weldb")))
