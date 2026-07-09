"""Tests for the query_welds.py script — pulling one panel's welds from the CSVs.

The script lives under ``scripts/`` (not on the package path), so it is imported
by adding that directory to ``sys.path`` here.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import query_welds  # noqa: E402

POINT_CSV = (
    "panel,weld_id,source,x0,y0,x1,y1,length\n"
    "N1,N1.T100,N1.weldb,10,20,15,25,3\n"
    "N1,N1.T101,N1.weldb,20,20,25,25,3\n"
    "N9,N9.T100,N9.weldb,10,20,15,25,3\n"
)
LINEAR_CSV = (
    "panel,weld_id,source,x0,y0,x1,y1\n"
    "N1,N1._A,N1.weldb,10,20,10,80\n"
)
AREA_CSV = "panel,weld_id,source,x0,y0,x1,y1\n"  # header only, no rows


@pytest.fixture
def csv_dir(tmp_path: Path) -> Path:
    (tmp_path / "point_welds.csv").write_text(POINT_CSV, encoding="utf-8")
    (tmp_path / "linear_welds.csv").write_text(LINEAR_CSV, encoding="utf-8")
    (tmp_path / "area_welds.csv").write_text(AREA_CSV, encoding="utf-8")
    return tmp_path


def test_query_filters_by_panel(csv_dir: Path):
    welds = query_welds.query_welds(csv_dir, "N1")
    assert [r["weld_id"] for r in welds["point"]] == ["N1.T100", "N1.T101"]
    assert [r["weld_id"] for r in welds["linear"]] == ["N1._A"]
    assert welds["area"] == []
    # N9's welds are not swept into N1's result.
    assert all(r["panel"] == "N1" for r in welds["point"])


def test_query_panel_match_is_case_insensitive(csv_dir: Path):
    assert len(query_welds.query_welds(csv_dir, "n1")["point"]) == 2


def test_query_type_filter_reads_only_requested_csv(csv_dir: Path):
    welds = query_welds.query_welds(csv_dir, "N1", types=["point"])
    assert set(welds) == {"point"}
    assert len(welds["point"]) == 2


def test_query_missing_csv_contributes_no_rows(tmp_path: Path):
    # No CSVs on disk at all -> every type comes back empty, no error.
    welds = query_welds.query_welds(tmp_path, "N1")
    assert welds == {"point": [], "linear": [], "area": []}


def test_rows_carry_the_bounding_box_rectangle(csv_dir: Path):
    row = query_welds.query_welds(csv_dir, "N1")["point"][0]
    # (x0,y0) top-left corner, (x1,y1) bottom-right corner of the weld box.
    assert (row["x0"], row["y0"], row["x1"], row["y1"]) == ("10", "20", "15", "25")


def test_summary_reports_counts_and_total(csv_dir: Path):
    welds = query_welds.query_welds(csv_dir, "N1")
    out = query_welds._format_summary("N1", welds)
    assert "point" in out and "N1.T100" in out
    assert "total" in out and "3" in out  # 2 point + 1 linear


def test_csv_output_tags_each_row_with_its_weld_type(csv_dir: Path):
    welds = query_welds.query_welds(csv_dir, "N1")
    text = query_welds._format_csv(welds)
    assert text.splitlines()[0].startswith("weld_type,")
    assert "point,N1,N1.T100" in text
    assert "linear,N1,N1._A" in text


def test_main_errors_when_no_csvs_present(tmp_path: Path, capsys):
    with pytest.raises(SystemExit) as exc:
        query_welds.main(["N1", "--csv-dir", str(tmp_path)])
    assert "No weld CSVs found" in str(exc.value)
