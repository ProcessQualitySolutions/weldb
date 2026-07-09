"""Tests for PDF-position -> HTML5-canvas conversion.

Covers the library function ``weldb.weld_canvas_boxes`` and the
``scripts/weld_positions_to_canvas.py`` CLI. These need ``fpdf2`` (the page is
measured from the rendered layout); the whole module is skipped without it.
"""

from __future__ import annotations

import json
import sys
import textwrap
from pathlib import Path

import pytest

import weldb

pytest.importorskip("fpdf", reason="canvas conversion needs fpdf2 to measure the page")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import weld_positions_to_canvas as w2c  # noqa: E402

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


@pytest.fixture
def doc():
    return weldb.loads(VALID)


@pytest.fixture
def page_dims(doc):
    env = weldb.weld_positions_from_doc(doc)
    return env["page_width"], env["page_height"]


def test_scale_is_keyed_to_canvas_width(doc, page_dims):
    page_w, _ = page_dims
    result = weldb.weld_canvas_boxes(doc, canvas_width=2 * page_w, canvas_height=10_000)
    assert result["scale"] == pytest.approx(2.0, abs=1e-4)
    assert result["units"] == "px" and result["origin"] == "top-left"


def test_pixels_are_mm_times_scale_no_flip(doc, page_dims):
    page_w, _ = page_dims
    scale = 3.0
    result = weldb.weld_canvas_boxes(doc, canvas_width=scale * page_w, canvas_height=10_000)
    boxes = weldb.first_view_weld_boxes(doc)  # mm, same source
    by_id = {w["weld_id"]: w for w in result["welds"]}
    # *T1 -> N5.T1 ; each corner is the mm corner times the width-derived scale.
    px = by_id["N5.T1"]
    mm = boxes["*T1"]
    assert px["x0"] == pytest.approx(mm["x0"] * scale, abs=0.02)
    assert px["y0"] == pytest.approx(mm["y0"] * scale, abs=0.02)
    assert px["cx"] == pytest.approx((mm["x0"] + mm["x1"]) / 2 * scale, abs=0.02)


def test_top_stays_top_bottom_stays_bottom(doc, page_dims):
    # No vertical flip: the top-row weld keeps a smaller y than the bottom-row one.
    page_w, _ = page_dims
    result = weldb.weld_canvas_boxes(doc, canvas_width=page_w, canvas_height=10_000)
    by_id = {w["weld_id"]: w for w in result["welds"]}
    assert by_id["N5.T1"]["cy"] < by_id["N5.B1"]["cy"]


def test_ids_are_panel_prefixed(doc, page_dims):
    page_w, _ = page_dims
    result = weldb.weld_canvas_boxes(doc, canvas_width=page_w, canvas_height=10_000)
    assert {w["weld_id"] for w in result["welds"]} == {"N5.A", "N5.T1", "N5.B", "N5.B1"}


def test_required_height_and_all_in_bounds_for_tall_canvas(doc, page_dims):
    page_w, page_h = page_dims
    result = weldb.weld_canvas_boxes(doc, canvas_width=page_w, canvas_height=page_h + 1)
    assert result["required_canvas_height"] == pytest.approx(page_h, abs=0.02)
    assert result["out_of_bounds"] == []
    assert all(w["in_bounds"] for w in result["welds"])


def test_short_canvas_flags_out_of_bounds(doc, page_dims):
    page_w, _ = page_dims
    result = weldb.weld_canvas_boxes(doc, canvas_width=page_w, canvas_height=1.0)
    # The bottom-row welds sit well below y=1px, so they must be flagged.
    assert "N5.B1" in result["out_of_bounds"]
    flagged = {w["weld_id"] for w in result["welds"] if not w["in_bounds"]}
    assert flagged == set(result["out_of_bounds"])


def test_nonpositive_canvas_rejected(doc):
    with pytest.raises(ValueError):
        weldb.weld_canvas_boxes(doc, canvas_width=0, canvas_height=100)
    with pytest.raises(ValueError):
        weldb.weld_canvas_boxes(doc, canvas_width=100, canvas_height=-5)


# --- CLI ---------------------------------------------------------------------


@pytest.fixture
def project(tmp_path):
    (tmp_path / "N5.weldb").write_text(VALID, encoding="utf-8")
    return tmp_path


def test_cli_emits_json_by_panel_name(project, page_dims, capsys):
    page_w, page_h = page_dims
    rc = w2c.main(["N5", "--width", str(page_w), "--height", str(page_h + 1), "--dir", str(project)])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["panel_name"] == "N5"
    assert len(payload["welds"]) == 4


def test_cli_accepts_a_direct_file_path(project, page_dims, capsys):
    page_w, page_h = page_dims
    rc = w2c.main([str(project / "N5.weldb"), "--width", str(page_w), "--height", str(page_h + 1)])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["panel_name"] == "N5"


def test_cli_fails_on_out_of_bounds(project, page_dims, capsys):
    page_w, _ = page_dims
    rc = w2c.main(["N5", "--width", str(page_w), "--height", "1", "--dir", str(project)])
    assert rc == 1
    err = capsys.readouterr().err
    assert "outside" in err and "N5.B1" in err


def test_cli_allow_out_of_bounds_emits_anyway(project, page_dims, capsys):
    page_w, _ = page_dims
    rc = w2c.main(
        ["N5", "--width", str(page_w), "--height", "1", "--dir", str(project), "--allow-out-of-bounds"]
    )
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["out_of_bounds"]


def test_cli_unknown_panel_errors(project):
    with pytest.raises(SystemExit):
        w2c.main(["N99", "--width", "1200", "--height", "900", "--dir", str(project)])
