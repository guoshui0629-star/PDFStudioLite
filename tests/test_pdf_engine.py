from __future__ import annotations

import hashlib
import io
from pathlib import Path

import pymupdf
from PIL import Image

from app.core.compression import TARGET_MAX_ERROR_BYTES, compress_to_target, lossless_optimize
from app.core.document import DocumentModel
from app.core.pdf_engine import export_pages, render_thumbnail


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def make_text_pdf(path: Path, labels: list[str]) -> None:
    doc = pymupdf.open()
    for label in labels:
        page = doc.new_page(width=300, height=400)
        page.insert_text((30, 50), label, fontsize=20)
    doc.save(path)
    doc.close()


def test_pdf_page_export_preserves_text_order_and_source(tmp_path: Path) -> None:
    source = tmp_path / "原始文档.pdf"
    output = tmp_path / "导出结果.pdf"
    make_text_pdf(source, ["FIRST", "SECOND", "THIRD"])
    before = digest(source)
    model = DocumentModel()
    model.add_files([source])
    model.apply_order([model.pages[2].uid, model.pages[0].uid, model.pages[1].uid])
    export_pages(model.pages, output)
    with pymupdf.open(output) as result:
        assert result.page_count == 3
        assert [page.get_text().strip() for page in result] == ["THIRD", "FIRST", "SECOND"]
    assert digest(source) == before


def test_image_export_keeps_pixel_dimensions_and_jpeg_encoding(tmp_path: Path) -> None:
    image_path = tmp_path / "照片.jpg"
    output = tmp_path / "图片合并.pdf"
    Image.new("RGB", (320, 180), (30, 80, 160)).save(image_path, "JPEG", quality=94)
    model = DocumentModel()
    model.add_files([image_path])
    export_pages(model.pages, output)
    with pymupdf.open(output) as result:
        images = result[0].get_images(full=True)
        assert len(images) == 1
        assert images[0][2:4] == (320, 180)
        extracted = result.extract_image(images[0][0])
        assert extracted["ext"] in {"jpeg", "jpg"}


def test_lossless_and_target_compression_outputs_openable_pdf(tmp_path: Path) -> None:
    source = tmp_path / "source.pdf"
    optimized = tmp_path / "optimized.pdf"
    compressed = tmp_path / "compressed.pdf"
    make_text_pdf(source, ["Selectable text"])
    lossless = lossless_optimize(source, optimized)
    assert lossless.output_bytes == optimized.stat().st_size
    with pymupdf.open(optimized) as result:
        assert "Selectable text" in result[0].get_text()
    target = compress_to_target(optimized, compressed, max(1, optimized.stat().st_size // 4))
    assert target.output_bytes == compressed.stat().st_size
    expected_reached = target.output_bytes <= target.target_bytes and target.target_bytes - target.output_bytes <= TARGET_MAX_ERROR_BYTES
    assert target.reached_target is expected_reached
    with pymupdf.open(compressed) as result:
        assert result.page_count == 1
        assert "Selectable text" in result[0].get_text()


def test_refuses_to_overwrite_source(tmp_path: Path) -> None:
    source = tmp_path / "same.pdf"
    make_text_pdf(source, ["safe"])
    model = DocumentModel()
    model.add_files([source])
    try:
        export_pages(model.pages, source)
    except ValueError as error:
        assert "不能覆盖" in str(error)
    else:
        raise AssertionError("Expected overwrite protection")


def test_target_compression_is_within_ten_percent_when_feasible(tmp_path: Path) -> None:
    image_path = tmp_path / "noise.jpg"
    source = tmp_path / "image-rich.pdf"
    output = tmp_path / "target.pdf"
    image = Image.effect_noise((1400, 1400), 72).convert("RGB")
    image.save(image_path, "JPEG", quality=100, subsampling=0)
    doc = pymupdf.open()
    for _ in range(3):
        page = doc.new_page(width=700, height=700)
        page.insert_image(page.rect, filename=str(image_path))
    doc.save(source)
    doc.close()
    target_bytes = int(source.stat().st_size * 0.62)
    result = compress_to_target(source, output, target_bytes)
    assert result.reached_target
    assert result.output_bytes <= target_bytes
    assert result.target_error_ratio is not None
    assert target_bytes - result.output_bytes <= TARGET_MAX_ERROR_BYTES


def test_page_gap_expands_all_but_last_page_without_rasterizing_text(tmp_path: Path) -> None:
    source = tmp_path / "gap-source.pdf"
    output = tmp_path / "gap-output.pdf"
    make_text_pdf(source, ["first", "second"])
    model = DocumentModel()
    model.add_files([source])
    export_pages(model.pages, output, page_gap_mm=10.0)
    with pymupdf.open(source) as original, pymupdf.open(output) as result:
        expected_gap = 10.0 * 72.0 / 25.4
        assert abs(result[0].mediabox.height - original[0].mediabox.height - expected_gap) < 0.1
        assert abs(result[1].mediabox.height - original[1].mediabox.height) < 0.1
        assert "first" in result[0].get_text()


def test_target_compression_fills_gap_by_reencoding_part_of_image_set(tmp_path: Path) -> None:
    source = tmp_path / "many-images.pdf"
    optimized = tmp_path / "many-images-optimized.pdf"
    output = tmp_path / "many-images-target.pdf"
    doc = pymupdf.open()
    for index in range(5):
        image_path = tmp_path / f"noise-{index}.png"
        Image.effect_noise((600, 600), 55 + index * 5).convert("RGB").save(image_path, "PNG")
        page = doc.new_page(width=600, height=600)
        page.insert_image(page.rect, filename=str(image_path))
    doc.save(source)
    doc.close()
    optimized_result = lossless_optimize(source, optimized)
    target_bytes = int(optimized_result.output_bytes * 0.72)
    result = compress_to_target(source, output, target_bytes)
    assert result.reached_target, result.message
    assert result.output_bytes <= target_bytes
    assert result.target_error_ratio is not None
    assert target_bytes - result.output_bytes <= TARGET_MAX_ERROR_BYTES
    assert target_bytes - result.output_bytes <= 128 * 1024


def test_uniform_a4_and_b5_pages_preserve_selectable_text(tmp_path: Path) -> None:
    source = tmp_path / "sized.pdf"
    make_text_pdf(source, ["vector text"])
    model = DocumentModel()
    model.add_files([source])
    for name, size_mm in (("a4.pdf", (210.0, 297.0)), ("b5.pdf", (176.0, 250.0))):
        output = tmp_path / name
        export_pages(model.pages, output, page_size_mm=size_mm)
        with pymupdf.open(output) as result:
            assert abs(result[0].rect.width - size_mm[0] * 72 / 25.4) < 0.2
            assert abs(result[0].rect.height - size_mm[1] * 72 / 25.4) < 0.2
            assert "vector text" in result[0].get_text()


def test_rotated_image_thumbnail_changes_orientation(tmp_path: Path) -> None:
    image_path = tmp_path / "wide.png"
    Image.new("RGB", (320, 120), "teal").save(image_path)
    model = DocumentModel()
    model.add_files([image_path])
    model.rotate([0], 90)
    thumbnail = Image.open(io.BytesIO(render_thumbnail(model.pages[0], 240)))
    assert thumbnail.height > thumbnail.width
