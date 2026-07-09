"""Tests for the disk-free library API (loads/dumps and the in-memory render
helpers).

These cover the string/bytes counterparts that let a caller parse and render
content without touching the filesystem: loads/dumps and the *_bytes / *_from_doc
render helpers — the same functions the skill's scripts rely on.
"""

from __future__ import annotations

import textwrap

import pytest

import weldb
from weldb.exceptions import MissingRequiredFieldError

VALID = textwrap.dedent(
    """\
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
              - ["", "", ""]
              - ["_A", "*B1", "_B"]
    """
)


def test_loads_parses_and_validates():
    doc = weldb.loads(VALID)
    assert doc["panel_name"] == "N5"
    # Grid normalization still applies (cells are strings).
    grid = doc["maps"][-1]["views"][0]["grid"]
    assert all(isinstance(c, str) for row in grid for c in row)


def test_loads_enforces_required_fields():
    with pytest.raises(MissingRequiredFieldError):
        weldb.loads("panel_name: N5")  # missing everything else


def test_loads_dumps_roundtrip_is_stable():
    doc = weldb.loads(VALID)
    text = weldb.dumps(doc)
    assert weldb.loads(text)["panel_name"] == "N5"
    # dumps output is itself valid weldb content.
    assert "panel_name: N5" in text


def test_dumps_matches_save(tmp_path):
    doc = weldb.loads(VALID)
    p = tmp_path / "N5.weldb"
    weldb.save(doc, p)
    assert p.read_text(encoding="utf-8") == weldb.dumps(doc)


def test_render_pdf_bytes_returns_pdf_without_writing(tmp_path):
    doc = weldb.loads(VALID)
    data = weldb.render_pdf_bytes(doc)
    assert data[:5] == b"%PDF-"
    # Nothing was written anywhere.
    assert list(tmp_path.iterdir()) == []


def test_render_pdf_bytes_matches_file_render(tmp_path):
    # The bytes path and the file path must produce the same drawing.
    src = tmp_path / "N5.weldb"
    src.write_text(VALID, encoding="utf-8")
    out = weldb.render_pdf(src, output_path=tmp_path / "N5.pdf")
    file_bytes = out.read_bytes()
    mem_bytes = weldb.render_pdf_bytes(weldb.loads(VALID))
    # PDF streams carry no timestamps here, so identical input → identical bytes.
    assert mem_bytes == file_bytes


def test_render_revision_history_pdf_bytes():
    data = weldb.render_revision_history_pdf_bytes(weldb.loads(VALID))
    assert data[:5] == b"%PDF-"


def test_weld_positions_from_doc_shape():
    doc = weldb.loads(VALID)
    data = weldb.weld_positions_from_doc(doc)
    assert data["panel_name"] == "N5"
    assert data["units"] == "mm" and data["origin"] == "top-left"
    weld = data["views"][0]["welds"][0]
    for k in ("id", "type", "x0", "y0", "x1", "y1"):
        assert k in weld


def test_first_view_weld_boxes_maps_every_weld_once():
    doc = weldb.loads(VALID)
    boxes = weldb.first_view_weld_boxes(doc)
    # Every grid weld label (with its type prefix) gets exactly one box.
    assert set(boxes) == {"_A", "*T1", "_B", "*B1"}
    for box in boxes.values():
        assert set(box) == {"x0", "y0", "x1", "y1"}
        assert box["x0"] <= box["x1"] and box["y0"] <= box["y1"]


def test_first_view_weld_boxes_uses_leftmost_view():
    # A weld drawn in two views is reported at its leftmost-view coordinates.
    doc = weldb.loads(VALID)
    # Duplicate the hot_side grid into a second view drawn to the right.
    grid = doc["maps"][-1]["views"][0]["grid"]
    doc["maps"][-1]["views"].append({"name": "cold_side", "grid": grid})

    boxes = weldb.first_view_weld_boxes(doc)
    data = weldb.weld_positions_from_doc(doc)
    left = next(w for w in data["views"][0]["welds"] if w["id"] == "*T1")
    right = next(w for w in data["views"][1]["welds"] if w["id"] == "*T1")

    # The reported box is the leftmost view's, not the right view's.
    assert boxes["*T1"]["x0"] == left["x0"]
    assert boxes["*T1"]["x0"] < right["x0"]
