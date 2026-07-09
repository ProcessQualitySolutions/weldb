"""Tests for weldb.validation — the project-wide weld-ID rule checker.

These cover the spec's uniqueness and naming rules, and in particular the case
the checker exists to settle: the SAME grid label on two different panels (two
panels on the same tubes at different elevations) is NOT a duplicate, because the
project ID is panel-prefixed.
"""

from __future__ import annotations

import textwrap

import weldb


def _panel(panel_name: str, grid: list[list[str]]) -> str:
    """Minimal valid .weldb YAML for a panel with one map and the given grid."""
    rows = "\n".join("              - " + str(row) for row in grid)
    return textwrap.dedent(
        f"""\
        panel_name: {panel_name}
        tube_mtrl: SA-210 A1
        tube_od: 2.0
        tube_wall: 0.15
        units: in
        elevation: 1850 in
        maps:
          - rev: R0
            date: 2026-01-01
            updated_by: test
            comments: init
            views:
              - name: hot_side
                grid:
        """
    ) + rows + "\n"


def _write(tmp_path, name: str, text: str):
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return p


def test_clean_project_has_no_issues(tmp_path):
    _write(tmp_path, "N5.weldb", _panel("N5", [["*T1", "*T2"]]))
    _write(tmp_path, "N6.weldb", _panel("N6", [["*T1", "*T2"]]))
    assert weldb.validate_project(tmp_path) == []


def test_same_labels_different_panels_is_not_a_duplicate(tmp_path):
    # N1 and N9 cover the same tubes at different elevations — the reported bug.
    _write(tmp_path, "N1.weldb", _panel("N1", [["*T100", "*T101", "*T102"]]))
    _write(tmp_path, "N9.weldb", _panel("N9", [["*T100", "*T101", "*T102"]]))
    issues = weldb.validate_project(tmp_path)
    assert issues == [], f"expected no issues, got {[str(i) for i in issues]}"


def test_duplicate_panel_name_flags_dup_and_point_welds(tmp_path):
    # A file mislabeled with an existing panel_name yields the same prefixed IDs.
    _write(tmp_path, "N1.weldb", _panel("N1", [["*T100"]]))
    _write(tmp_path, "N1copy.weldb", _panel("N1", [["*T100"]]))  # panel_name clashes
    codes = {i.code for i in weldb.validate_project(tmp_path)}
    assert "duplicate_panel_name" in codes
    assert "panel_name_mismatch" in codes  # N1 != stem "N1copy"
    assert "duplicate_point_weld" in codes  # both resolve to N1.T100


def test_panel_name_must_match_filename(tmp_path):
    _write(tmp_path, "N2.weldb", _panel("N3", [["*T1"]]))
    issues = weldb.validate_project(tmp_path)
    assert [i.code for i in issues] == ["panel_name_mismatch"]


def test_duplicate_point_weld_within_view_is_invalid_grid(tmp_path):
    _write(tmp_path, "N5.weldb", _panel("N5", [["*T1", "*T1"]]))
    issues = weldb.validate_project(tmp_path)
    assert [i.code for i in issues] == ["invalid_weld_grid"]


def test_conflicting_base_id_across_types_is_invalid_grid(tmp_path):
    # *T5 and _T5 share base ID T5 — a collision in the weld log.
    _write(tmp_path, "N5.weldb", _panel("N5", [["*T5", "_T5"]]))
    codes = [i.code for i in weldb.validate_project(tmp_path)]
    assert codes == ["invalid_weld_grid"]


def test_unloadable_file_is_reported_not_raised(tmp_path):
    _write(tmp_path, "BAD.weldb", "panel_name: BAD\n")  # missing required fields
    issues = weldb.validate_project(tmp_path)
    assert [i.code for i in issues] == ["load_error"]


def test_reports_every_problem_not_just_the_first(tmp_path):
    _write(tmp_path, "N5.weldb", _panel("N5", [["*T1"]]))
    _write(tmp_path, "BAD.weldb", "panel_name: BAD\n")
    _write(tmp_path, "N7.weldb", _panel("WRONG", [["*T1"]]))  # name mismatch
    issues = weldb.validate_project(tmp_path)
    codes = sorted(i.code for i in issues)
    assert codes == ["load_error", "panel_name_mismatch"]
