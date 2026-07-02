"""Tests for weldb.document — loading, validation, and grid normalization."""

from __future__ import annotations

import textwrap

import pytest
import yaml

from weldb.document import _next_rev, add_revision, load
from weldb.exceptions import InvalidFileExtensionError, MissingRequiredFieldError
from weldb.welds import _current_views


def _write(tmp_path, text: str, name: str = "N5.weldb"):
    p = tmp_path / name
    p.write_text(textwrap.dedent(text), encoding="utf-8")
    return p


VALID = """\
    panel_name: N5
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
              - ["_A", "*T1", "_B"]
"""


def test_load_rejects_bad_extension(tmp_path):
    p = tmp_path / "N5.txt"
    p.write_text("panel_name: N5", encoding="utf-8")
    with pytest.raises(InvalidFileExtensionError):
        load(p)


def test_load_valid_file(tmp_path):
    doc = load(_write(tmp_path, VALID))
    assert doc["panel_name"] == "N5"


def test_load_empty_file_raises_missing_field(tmp_path):
    # H5: an empty file parses to None and must be rejected cleanly, not crash
    # downstream with a raw subscript error.
    p = _write(tmp_path, "")
    with pytest.raises(MissingRequiredFieldError):
        load(p)


@pytest.mark.parametrize(
    "missing", ["panel_name", "tube_mtrl", "tube_od", "tube_wall", "units", "elevation", "maps"]
)
def test_load_enforces_all_required_fields(tmp_path, missing):
    # H5: REQUIRED_FIELDS must all be enforced, not just elevation.
    doc = yaml.safe_load(textwrap.dedent(VALID))
    del doc[missing]
    p = tmp_path / "N5.weldb"
    p.write_text(yaml.safe_dump(doc), encoding="utf-8")
    with pytest.raises(MissingRequiredFieldError) as exc:
        load(p)
    assert missing in str(exc.value)


def test_load_empty_elevation_rejected(tmp_path):
    text = VALID.replace("elevation: 1850 in", "elevation: '   '")
    with pytest.raises(MissingRequiredFieldError):
        load(_write(tmp_path, text))


def test_load_coerces_numeric_cells_to_str(tmp_path):
    # M2: unquoted numeric cells must not crash extraction.
    text = VALID.replace('["_A", "*T1", "_B"]', "[250, '*T250']")
    doc = load(_write(tmp_path, text))
    grid = _current_views(doc)[0]["grid"]
    assert grid[0] == ["250", "*T250"]
    assert all(isinstance(c, str) for row in grid for c in row)


def test_load_pads_ragged_rows(tmp_path):
    # M3: ragged grids must be padded to rectangular at load time.
    text = VALID.replace(
        '              - ["_A", "*T1", "_B"]',
        '              - ["_A", "*T1", "_B"]\n              - ["x"]',
    )
    doc = load(_write(tmp_path, text))
    grid = _current_views(doc)[0]["grid"]
    assert len(grid[0]) == len(grid[1]) == 3
    assert grid[1] == ["x", "", ""]


@pytest.mark.parametrize(
    "prev,expected",
    [(None, "R0"), ("", "R0"), ("R0", "R1"), ("R9", "R10"), ("A3", "A4"), ("rev", "rev-1")],
)
def test_next_rev(prev, expected):
    assert _next_rev(prev) == expected


def test_add_revision_appends_and_increments(tmp_path):
    doc = load(_write(tmp_path, VALID))
    add_revision(doc, updated_by="me", comments="second")
    assert len(doc["maps"]) == 2
    assert doc["maps"][-1]["rev"] == "R1"
    assert doc["maps"][-1]["comments"] == "second"
