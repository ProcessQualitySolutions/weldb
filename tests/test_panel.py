"""Tests for the high-level panel operations: save_panel and archive_panel.

These cover the "always render on save" behavior (a save also renders the derived
PDF) and the archive-not-delete behavior (a panel's whole file set moves together,
and repeated archiving of the same panel name is non-destructive and
batch-consistent).
"""

from __future__ import annotations

import textwrap

import pytest

import weldb
from weldb.exceptions import InvalidFileExtensionError

pytest.importorskip("fpdf", reason="save_panel/archive rendering needs fpdf2")

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


def _write_panel_set(tmp_path, stem="N5"):
    """Create <stem>.weldb and its rendered artifacts; return the source path."""
    doc = weldb.loads(VALID)
    src = tmp_path / f"{stem}.weldb"
    weldb.save_panel(doc, src)
    return src


def test_save_panel_writes_yaml_and_pdf(tmp_path):
    doc = weldb.loads(VALID)
    src = tmp_path / "N5.weldb"
    written = weldb.save_panel(doc, src)

    assert written["weldb"] == src and src.exists()
    assert written["pdf"] == tmp_path / "N5.pdf" and written["pdf"].exists()
    # Weld positions are no longer a per-panel JSON — they live in the CSVs.
    assert "weld_positions" not in written
    assert not (tmp_path / "N5_weld_positions.json").exists()
    assert "revisions_pdf" not in written


def test_save_panel_reload_roundtrips(tmp_path):
    src = _write_panel_set(tmp_path)
    # The YAML written by save_panel must load back to the same document.
    assert weldb.load(src) == weldb.loads(VALID)


def test_save_panel_revisions_flag_adds_history_pdf(tmp_path):
    doc = weldb.loads(VALID)
    written = weldb.save_panel(doc, tmp_path / "N5.weldb", revisions=True)
    assert written["revisions_pdf"] == tmp_path / "N5_revisions.pdf"
    assert written["revisions_pdf"].exists()


def test_save_panel_rejects_bad_extension(tmp_path):
    doc = weldb.loads(VALID)
    with pytest.raises(InvalidFileExtensionError):
        weldb.save_panel(doc, tmp_path / "N5.txt")


def test_archive_moves_the_whole_panel_set(tmp_path):
    src = _write_panel_set(tmp_path)
    weldb.save_panel(weldb.load(src), src, revisions=True)  # add the revisions PDF too

    moved = weldb.archive_panel(src)
    names = sorted(p.name for p in moved)
    assert names == ["N5.pdf", "N5.weldb", "N5_revisions.pdf"]
    # Everything left the project root and landed in archive/.
    assert not src.exists()
    assert not (tmp_path / "N5.pdf").exists()
    for p in moved:
        assert p.parent == tmp_path / "archive"
        assert p.exists()


def test_archive_skips_missing_artifacts(tmp_path):
    doc = weldb.loads(VALID)
    src = tmp_path / "N5.weldb"
    weldb.save(doc, src)  # only the .weldb exists (no render)

    moved = weldb.archive_panel(src)
    assert [p.name for p in moved] == ["N5.weldb"]


def test_repeated_archive_is_batch_consistent(tmp_path):
    """A panel redesigned and re-archived keeps each generation grouped by _N."""
    for _ in range(3):
        src = _write_panel_set(tmp_path)  # re-creates N5.weldb + artifacts
        weldb.archive_panel(src)

    archive = tmp_path / "archive"
    got = sorted(p.name for p in archive.iterdir())
    assert got == sorted([
        "N5.pdf", "N5.weldb",
        "N5_1.pdf", "N5_1.weldb",
        "N5_2.pdf", "N5_2.weldb",
    ])
    # Each generation's files carry a consistent tag (no drift).
    for tag in ("", "_1", "_2"):
        assert (archive / f"N5{tag}.weldb").exists()
        assert (archive / f"N5{tag}.pdf").exists()


def test_archive_custom_dir(tmp_path):
    src = _write_panel_set(tmp_path)
    dest = tmp_path / "retired"
    moved = weldb.archive_panel(src, dest)
    assert all(p.parent == dest for p in moved)


def test_archive_rejects_non_weldb(tmp_path):
    p = tmp_path / "N5.pdf"
    p.write_text("x", encoding="utf-8")
    with pytest.raises(InvalidFileExtensionError):
        weldb.archive_panel(p)


def test_derived_artifact_paths(tmp_path):
    src = tmp_path / "N5.weldb"
    paths = weldb.derived_artifact_paths(src, revisions=True)
    assert paths["pdf"] == tmp_path / "N5.pdf"
    assert "weld_positions" not in paths
    assert paths["revisions_pdf"] == tmp_path / "N5_revisions.pdf"
