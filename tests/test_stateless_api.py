"""Tests for the disk-free library API (loads/dumps and the in-memory render
helpers).

These cover the string/bytes counterparts that let a caller parse and render
content without touching the filesystem: loads/dumps and the *_bytes / *_from_doc
/ *_data render helpers — the same functions the skill's scripts rely on.
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


def test_weld_positions_data_from_doc_with_canvas():
    doc = weldb.loads(VALID)
    data = weldb.weld_positions_data(doc, canvas_w=1000, canvas_h=800)
    assert data["panel_name"] == "N5"
    assert data["canvas_w"] == 1000
    weld = data["views"][0]["welds"][0]
    for k in ("x0", "y0", "x1", "y1", "px0", "py0", "px1", "py1"):
        assert k in weld


def test_weld_positions_data_requires_both_canvas_dims():
    doc = weldb.loads(VALID)
    with pytest.raises(ValueError):
        weldb.weld_positions_data(doc, canvas_w=1000)


def test_render_panel_bundle_matches_separate_renders():
    # The one-pass bundle must produce byte/shape-identical results to rendering
    # the PDF and computing the positions separately (proving the refactor is
    # equivalent, just cheaper).
    doc = weldb.loads(VALID)
    bundle = weldb.render_panel_bundle(doc, color=True, canvas_w=1000, canvas_h=800)
    assert bundle["pdf_bytes"] == weldb.render_pdf_bytes(doc, color=True)
    assert bundle["positions"] == weldb.weld_positions_data(
        doc, canvas_w=1000, canvas_h=800
    )


def test_render_panel_bundle_without_canvas_has_no_pixels():
    doc = weldb.loads(VALID)
    bundle = weldb.render_panel_bundle(doc)
    assert bundle["pdf_bytes"][:5] == b"%PDF-"
    assert "canvas_w" not in bundle["positions"]
    assert "px0" not in bundle["positions"]["views"][0]["welds"][0]


def test_render_panel_bundle_requires_both_canvas_dims():
    doc = weldb.loads(VALID)
    with pytest.raises(ValueError):
        weldb.render_panel_bundle(doc, canvas_w=1000)
