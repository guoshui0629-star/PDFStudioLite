from __future__ import annotations

from pathlib import Path

import pymupdf
from PIL import Image

from app.core.document import DocumentModel
from app.ui.page_grid import reordered_uids


def make_pdf(path: Path, labels: list[str]) -> None:
    doc = pymupdf.open()
    for label in labels:
        page = doc.new_page()
        page.insert_text((72, 72), label, fontsize=18)
    doc.save(path)
    doc.close()


def test_insert_order_delete_undo_redo(tmp_path: Path) -> None:
    source = tmp_path / "source.pdf"
    image = tmp_path / "insert.png"
    make_pdf(source, ["one", "two", "three"])
    Image.new("RGB", (64, 32), "navy").save(image)
    model = DocumentModel()
    model.add_files([source])
    model.add_files([image], position=1)
    assert [page.source.name for page in model.pages] == ["source.pdf", "insert.png", "source.pdf", "source.pdf"]
    removed = model.delete([0, 2])
    assert len(removed) == 2
    assert len(model.pages) == 2
    assert model.undo()
    assert len(model.pages) == 4
    assert model.redo()
    assert len(model.pages) == 2


def test_duplicate_rotate_and_reorder(tmp_path: Path) -> None:
    source = tmp_path / "source.pdf"
    make_pdf(source, ["one", "two"])
    model = DocumentModel()
    model.add_files([source])
    model.duplicate([0])
    model.rotate([1], 90)
    assert model.pages[1].rotation == 90
    uids = [page.uid for page in reversed(model.pages)]
    model.apply_order(uids)
    assert [page.uid for page in model.pages] == uids


def test_drag_reorder_inserts_before_and_after_target() -> None:
    uids = ["a", "b", "c", "d"]
    assert reordered_uids(uids, [1], 3) == ["a", "c", "b", "d"]
    assert reordered_uids(uids, [2], 1) == ["a", "c", "b", "d"]
    assert reordered_uids(uids, [1, 2], 4) == ["a", "d", "b", "c"]
    pages = ["1", "2", "3", "4", "5", "6", "7"]
    assert reordered_uids(pages, [3], 6) == ["1", "2", "3", "5", "6", "4", "7"]


def test_reset_clears_pages_and_history(tmp_path: Path) -> None:
    source = tmp_path / "source.pdf"
    make_pdf(source, ["one"])
    model = DocumentModel()
    model.add_files([source])
    model.reset()
    assert model.pages == []
    assert not model.can_undo
    assert not model.can_redo


def test_relative_move_preserves_selected_page_order(tmp_path: Path) -> None:
    source = tmp_path / "move.pdf"
    make_pdf(source, ["1", "2", "3", "4", "5", "6", "7"])
    model = DocumentModel()
    model.add_files([source])
    original = [page.uid for page in model.pages]
    model.move_relative([3], 1)
    assert [page.uid for page in model.pages] == original[:3] + [original[4], original[3]] + original[5:]
    model.move_relative([3, 4], -1)
    assert [page.uid for page in model.pages][2:4] == [original[4], original[3]]


def test_estimated_size_updates_when_image_is_added(tmp_path: Path) -> None:
    source = tmp_path / "source.pdf"
    image = tmp_path / "added.png"
    make_pdf(source, ["one", "two"])
    Image.new("RGB", (300, 200), "orange").save(image)
    model = DocumentModel()
    model.add_files([source])
    before = model.estimated_bytes
    model.add_files([image])
    assert model.estimated_bytes == before + image.stat().st_size
    model.duplicate([2])
    assert model.estimated_bytes == before + image.stat().st_size * 2
