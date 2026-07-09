"""High-level panel operations: save-with-render, and archive-not-delete.

These orchestrate the lower-level :mod:`weldb.document` and :mod:`weldb.render`
functions so a caller can express the two whole-panel operations in a single
call:

* :func:`save_panel` — write a ``.weldb`` file **and** regenerate every derived
  artifact (the drawing PDF and the weld-position JSON) in one shot. This is the
  "always render on save" rule (see ``references/weldb_design_philosophy.md``):
  the ``.weldb`` YAML is the source of truth, and its PDF/JSON are never allowed
  to lag behind it — every create or update re-derives them immediately.
* :func:`archive_panel` — retire a panel by **moving** its ``.weldb`` file and
  all of its derived artifacts together into an archive folder, rather than
  deleting anything.

Both live here (not in ``document.py``) because they depend on the renderer, and
``render.py`` already imports ``document.py`` — putting them in ``document`` would
be a circular import.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from weldb.document import FILE_EXTENSION, save
from weldb.exceptions import InvalidFileExtensionError
from weldb.render import render_panel_bundle, render_revision_history_pdf

# The derived-artifact suffixes that belong to a panel, keyed by role. Kept in
# one place so save/archive/prune all agree on the canonical file names.
_PDF_SUFFIX = ".pdf"
_POSITIONS_SUFFIX = "_weld_positions.json"
_REVISIONS_SUFFIX = "_revisions.pdf"


def derived_artifact_paths(
    source_path: str | Path, *, revisions: bool = False
) -> dict[str, Path]:
    """Return the canonical derived-artifact paths for a panel ``.weldb`` file.

    The paths are computed from the source's stem and directory; the files need
    not exist. Always includes ``"pdf"`` (``<stem>.pdf``) and ``"weld_positions"``
    (``<stem>_weld_positions.json``). When ``revisions`` is true, also includes
    ``"revisions_pdf"`` (``<stem>_revisions.pdf``).
    """
    source_path = Path(source_path)
    stem = source_path.stem
    parent = source_path.parent
    paths = {
        "pdf": parent / f"{stem}{_PDF_SUFFIX}",
        "weld_positions": parent / f"{stem}{_POSITIONS_SUFFIX}",
    }
    if revisions:
        paths["revisions_pdf"] = parent / f"{stem}{_REVISIONS_SUFFIX}"
    return paths


def save_panel(
    doc: dict[str, Any],
    path: str | Path,
    *,
    color: bool = True,
    canvas_w: float | None = None,
    canvas_h: float | None = None,
    revisions: bool = False,
    render: bool = True,
) -> dict[str, Path]:
    """Save a ``.weldb`` document **and** regenerate its derived artifacts.

    This is the one-shot "always render on save" entry point: it writes the YAML
    (validating the extension, exactly like :func:`weldb.save`) and then, unless
    ``render`` is false, immediately re-renders the drawing PDF (``<stem>.pdf``)
    and writes the weld-position map (``<stem>_weld_positions.json``) beside it,
    so the derived artifacts can never go stale relative to the source.

    - ``color`` — tint the PDF's cells/legend by weld type (default; pass
      ``color=False`` for black-on-white).
    - ``canvas_w`` / ``canvas_h`` — when **both** are given, the weld-position
      JSON additionally carries integer pixel corners scaled to that canvas.
    - ``revisions`` — also render the full revision-history PDF
      (``<stem>_revisions.pdf``).
    - ``render=False`` — write only the YAML (e.g. a caller that will render
      separately, or a sandbox without ``fpdf2``).

    The YAML is always written first, so a rendering failure (e.g. ``fpdf2`` not
    installed, which raises :class:`ImportError`) leaves the source of truth on
    disk; the exception then propagates for the caller to handle.

    Returns a dict of ``{role: Path}`` for everything written — always ``"weldb"``,
    plus ``"pdf"`` / ``"weld_positions"`` (and ``"revisions_pdf"`` when requested)
    when rendered.
    """
    path = Path(path)
    save(doc, path)  # validates the .weldb extension and writes the YAML
    written: dict[str, Path] = {"weldb": path}
    if not render:
        return written

    # One layout pass produces both the PDF and the weld-position map.
    paths = derived_artifact_paths(path)
    bundle = render_panel_bundle(doc, color=color, canvas_w=canvas_w, canvas_h=canvas_h)
    paths["pdf"].write_bytes(bundle["pdf_bytes"])
    paths["weld_positions"].write_text(
        json.dumps(bundle["positions"], indent=2), encoding="utf-8"
    )
    written["pdf"] = paths["pdf"]
    written["weld_positions"] = paths["weld_positions"]
    if revisions:
        written["revisions_pdf"] = render_revision_history_pdf(path)
    return written


def _split_panel_name(name: str) -> tuple[str, str]:
    """Split a panel file name into (base-without-suffix, suffix).

    ``_weld_positions.json`` and ``_revisions.pdf`` are compound suffixes and are
    peeled off whole, so a disambiguator lands before the real extension
    (``N9_weld_positions.json`` -> ``N9`` + ``_weld_positions.json``, not
    ``N9_weld_positions`` + ``.json``).
    """
    for compound in (_POSITIONS_SUFFIX, _REVISIONS_SUFFIX):
        if name.endswith(compound):
            return name[: -len(compound)], compound
    stem, dot, ext = name.rpartition(".")
    return (stem, f".{ext}") if dot else (name, "")


def _batch_suffix_index(archive_dir: Path, names: list[str]) -> int:
    """Smallest ``n`` such that NO name in ``names`` collides once tagged ``_n``.

    Archiving is non-destructive and **batch-consistent**: a whole archive
    generation shares one disambiguator so a panel that is redesigned and
    re-archived several times (e.g. ``N9`` scoped, cut, and rescoped) keeps each
    generation grouped — ``N9.*``, then ``N9_1.*``, then ``N9_2.*`` — rather than
    letting individual files drift onto different suffixes. ``n == 0`` means the
    names are all free and no suffix is added.
    """
    n = 0
    while True:
        clash = any((archive_dir / _tagged_name(name, n)).exists() for name in names)
        if not clash:
            return n
        n += 1


def _tagged_name(name: str, n: int) -> str:
    """``name`` unchanged when ``n == 0``, else with a ``_n`` before its suffix."""
    if n == 0:
        return name
    base, suffix = _split_panel_name(name)
    return f"{base}_{n}{suffix}"


def archive_panel(
    source_path: str | Path,
    archive_dir: str | Path | None = None,
    *,
    revisions: bool = True,
) -> list[Path]:
    """Retire a panel by **moving** its ``.weldb`` and all derived files to archive.

    Instead of deleting anything, every file that belongs to the panel — the
    ``.weldb`` source plus its ``.pdf``, ``_weld_positions.json`` and (when
    ``revisions``) ``_revisions.pdf`` — is moved **together** into ``archive_dir``,
    keeping the panel's full revision history intact for audit. This is the
    supported way to remove a panel from active scope; panels are never deleted
    outright (see ``references/project_spec.md``).

    - ``archive_dir`` — destination folder; defaults to an ``archive/`` directory
      beside the source. Created if it does not exist.
    - Missing artifacts are simply skipped (only files that exist are moved).
    - Archiving is non-destructive **and batch-consistent**: if the same panel
      was archived before, this whole generation is moved under a shared ``_N``
      suffix (``N9.*`` -> ``N9_1.*`` -> ``N9_2.*``), so redesigning a panel
      several times outside the normal revision process keeps each archived
      generation grouped and never overwrites an earlier one.

    Returns the list of destination paths that were moved (source first).
    Raises :class:`InvalidFileExtensionError` if ``source_path`` is not a
    ``.weldb`` file.
    """
    source_path = Path(source_path)
    if source_path.suffix != FILE_EXTENSION:
        raise InvalidFileExtensionError(str(source_path), FILE_EXTENSION)

    archive_dir = (
        Path(archive_dir) if archive_dir is not None else source_path.parent / "archive"
    )
    archive_dir.mkdir(parents=True, exist_ok=True)

    candidates = [source_path, *derived_artifact_paths(source_path, revisions=revisions).values()]
    present = [src for src in candidates if src.exists()]
    # One disambiguator for the whole generation, computed from the files that
    # actually exist, so every moved file shares the same ``_N`` tag.
    n = _batch_suffix_index(archive_dir, [src.name for src in present])

    moved: list[Path] = []
    for src in present:
        dest = archive_dir / _tagged_name(src.name, n)
        shutil.move(str(src), str(dest))
        moved.append(dest)
    return moved
