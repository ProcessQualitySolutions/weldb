"""Tests for weld extraction, tallies, property resolution, and export."""

from __future__ import annotations

import csv

import pytest

from weldb.export import to_csv, to_json
from weldb.models import AreaWeld, LinearWeld, PointWeld
from weldb.render import _area_weld_tally, _linear_weld_length_tally
from weldb.weld_log import prefix_weld_id
from weldb.welds import (
    get_area_welds,
    get_linear_welds,
    get_point_welds,
    resolve_weld_properties,
)


def make_doc(grid, **top):
    doc = {
        "panel_name": "N5",
        "tube_mtrl": "SA-210",
        "tube_od": 2.0,
        "tube_wall": 0.15,
        "units": "in",
        "elevation": "1850 in",
        "maps": [{"rev": "R0", "views": [{"name": "hot_side", "grid": grid}]}],
    }
    doc.update(top)
    return doc


# --- H1: area welds must export as type "area", not "linear" ---

def test_area_weld_to_csv_type(tmp_path):
    out = tmp_path / "welds.csv"
    to_csv([AreaWeld(weld_id="@CLAD1", cells=[(0, 0)])], out)
    rows = list(csv.reader(out.open(encoding="utf-8")))
    assert rows[1][0] == "area"


def test_area_weld_to_json_type(tmp_path):
    out = tmp_path / "welds.json"
    to_json([AreaWeld(weld_id="@CLAD1", cells=[(0, 0)])], out)
    import json

    data = json.loads(out.read_text(encoding="utf-8"))
    assert data[0]["type"] == "area"


def test_mixed_export_types(tmp_path):
    out = tmp_path / "welds.csv"
    to_csv(
        [
            PointWeld(weld_id="*T1", row=0, col=0),
            LinearWeld(weld_id="_A", cells=[(0, 1)]),
            AreaWeld(weld_id="@C", cells=[(0, 2)]),
        ],
        out,
    )
    rows = list(csv.reader(out.open(encoding="utf-8")))
    assert [r[0] for r in rows[1:]] == ["point", "linear", "area"]


# --- H2: area tally must not truncate fractional dimensions ---

def test_area_tally_uses_float():
    doc = make_doc(
        [["@C"]],
        weld_overrides={"@C": {"length": 2.5, "height": 3.5}},
    )
    all_dims, total = _area_weld_tally(doc)
    assert all_dims is True
    assert total == pytest.approx(8.75)


def test_area_tally_string_dimensions():
    doc = make_doc([["@C"]], weld_overrides={"@C": {"length": "2", "height": "3"}})
    all_dims, total = _area_weld_tally(doc)
    assert all_dims is True
    assert total == pytest.approx(6.0)


def test_linear_tally_none_present():
    doc = make_doc([["*T1"]])
    assert _linear_weld_length_tally(doc) == (False, 0.0)


# --- extraction ---

def test_extract_all_weld_types():
    doc = make_doc([["_A", "*T1", "@C"]])
    assert {w.weld_id for w in get_point_welds(doc)} == {"*T1"}
    assert {w.weld_id for w in get_linear_welds(doc)} == {"_A"}
    assert {w.weld_id for w in get_area_welds(doc)} == {"@C"}


# --- L4: resolve_weld_properties excludes bool and panel_name ---

def test_resolve_properties_excludes_bool_and_identity():
    doc = make_doc([["*T1"]], is_repair=True, client="Acme")
    props = resolve_weld_properties(doc)["*T1"]
    assert "is_repair" not in props  # bool excluded
    assert "panel_name" not in props  # identity excluded
    assert props["client"] == "Acme"  # custom string kept
    assert props["tube_mtrl"] == "SA-210"  # panel property kept


# --- L7: prefix_weld_id strips only the single type prefix ---

@pytest.mark.parametrize(
    "wid,expected",
    [("*T250", "N5.T250"), ("_A", "N5.A"), ("@C", "N5.C"), ("T5", "N5.T5"), ("__X", "N5._X")],
)
def test_prefix_weld_id(wid, expected):
    assert prefix_weld_id("N5", wid) == expected
