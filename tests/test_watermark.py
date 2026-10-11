from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pymupdf
from PIL import Image

from app.core.watermark import (
    WatermarkAsset,
    WatermarkSpec,
    apply_watermark,
    parse_page_range,
    remove_watermarks,
    scan_watermarks,
)


def make_source(path: Path) -> None:
    document = pymupdf.open()
    for number in range(3):
        page = document.new_page(width=300, height=200)
        page.insert_text((30, 50), f"BODY PAGE {number + 1}", fontsize=18)
    document.save(path)
    document.close()


def watermark_asset() -> WatermarkAsset:
    stream = BytesIO()
    Image.new("RGBA", (240, 80), (230, 110, 20, 90)).save(stream, "PNG")
    return WatermarkAsset(stream.getvalue(), 120, 40)


def test_parse_page_range() -> None:
    assert parse_page_range("1-2, 4，6-7", 8) == (0, 1, 3, 5, 6)


def test_parse_page_range_rejects_invalid_values() -> None:
    for expression in ("", "3-1", "1,,2", "0", "1-9", "A"):
        try:
            parse_page_range(expression, 8)
        except ValueError:
            continue
        raise AssertionError(f"应拒绝无效页码：{expression}")


def test_own_watermark_is_tracked_and_removable_without_changing_body_stream(tmp_path: Path) -> None:
    source = tmp_path / "原始.pdf"
    marked = tmp_path / "已加水印.pdf"
    removed = tmp_path / "已移除.pdf"
    make_source(source)
    spec = WatermarkSpec(label="内部文件", tiled=True, horizontal_gap=30, vertical_gap=30)

    record = apply_watermark(source, marked, watermark_asset(), spec, (0, 2))

    assert record.pages == (1, 3)
    assert record.stream_count > 2
    assert record.removable
    scanned = scan_watermarks(marked)
    assert scanned == [record]
    with pymupdf.open(source) as before, pymupdf.open(marked) as after:
        assert before[0].get_text() == after[0].get_text()
        assert before[1].get_text() == after[1].get_text()
        assert before[0].get_pixmap().digest != after[0].get_pixmap().digest
        assert before[1].get_pixmap().digest == after[1].get_pixmap().digest

    removed_records = remove_watermarks(marked, removed, (record.watermark_id,))

    assert removed_records == (record,)
    assert scan_watermarks(removed) == []
    with pymupdf.open(source) as before, pymupdf.open(removed) as after:
        assert before.page_count == after.page_count
        for page_number in range(before.page_count):
            assert before[page_number].get_text("rawdict") == after[page_number].get_text("rawdict")
            original_streams = [before.xref_stream(xref) for xref in before[page_number].get_contents()]
            retained_streams = [after.xref_stream(xref) for xref in after[page_number].get_contents()]
            assert original_streams == retained_streams


def test_source_pdf_is_never_modified(tmp_path: Path) -> None:
    source = tmp_path / "source.pdf"
    output = tmp_path / "output.pdf"
    make_source(source)
    original = source.read_bytes()
    apply_watermark(source, output, watermark_asset(), WatermarkSpec(), (0, 1, 2))
    assert source.read_bytes() == original


def test_repeated_text_is_detected_but_cannot_be_deleted(tmp_path: Path) -> None:
    source = tmp_path / "repeated.pdf"
    output = tmp_path / "unsafe.pdf"
    document = pymupdf.open()
    for _ in range(3):
        page = document.new_page(width=300, height=200)
        page.insert_text((90, 100), "CONFIDENTIAL", fontsize=18)
    document.save(source)
    document.close()
    suspected = next(record for record in scan_watermarks(source) if record.source == "suspected-text")
    assert not suspected.removable
    try:
        remove_watermarks(source, output, (suspected.watermark_id,))
    except ValueError as error:
        assert "无法安全移除" in str(error)
    else:
        raise AssertionError("疑似正文文字不应允许删除")


def test_independent_watermark_annotation_is_detected_and_removed(tmp_path: Path) -> None:
    source = tmp_path / "annotation.pdf"
    output = tmp_path / "annotation-removed.pdf"
    document = pymupdf.open()
    page = document.new_page(width=300, height=200)
    page.insert_text((20, 30), "BODY")
    annotation = page.add_freetext_annot(pymupdf.Rect(60, 70, 240, 120), "WATERMARK")
    annotation.set_info(subject="Independent watermark")
    document.xref_set_key(annotation.xref, "Subtype", "/Watermark")
    document.save(source)
    document.close()
    record = next(record for record in scan_watermarks(source) if record.source == "watermark-annotation")
    assert record.removable
    remove_watermarks(source, output, (record.watermark_id,))
    with pymupdf.open(output) as result:
        assert list(result[0].annots(types=[pymupdf.PDF_ANNOT_WATERMARK]) or []) == []
        assert result[0].get_text().strip() == "BODY"
