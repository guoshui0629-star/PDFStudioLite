from __future__ import annotations

from pathlib import Path

import pymupdf
from PIL import Image

from app.core.document import DocumentModel
from app.services.image_export import export_page_images


def make_pdf(path: Path) -> None:
    doc = pymupdf.open()
    for label in ("one", "two", "three"):
        page = doc.new_page(width=144, height=72)
        page.insert_text((20, 30), label)
    doc.save(path)
    doc.close()


def test_selected_pages_export_with_continuous_names_and_real_dpi(tmp_path: Path) -> None:
    source = tmp_path / "中文资料.pdf"
    output = tmp_path / "图片"
    make_pdf(source)
    model = DocumentModel()
    model.add_files([source])
    selected = [model.pages[1], model.pages[2]]
    result = export_page_images(selected, output, "测试", "PNG", 200)
    outputs = result["outputs"]
    assert [path.name for path in outputs] == ["测试1.png", "测试2.png"]
    with Image.open(outputs[0]) as image:
        assert image.size == (400, 200)


def test_jpg_export_avoids_existing_filename(tmp_path: Path) -> None:
    source = tmp_path / "source.pdf"
    make_pdf(source)
    existing = tmp_path / "页面1.jpg"
    existing.write_bytes(b"keep")
    model = DocumentModel()
    model.add_files([source])
    result = export_page_images([model.pages[0]], tmp_path, "页面", "JPG", 96, 85)
    output = result["outputs"][0]
    assert output.name == "页面1_2.jpg"
    assert existing.read_bytes() == b"keep"
    with Image.open(output) as image:
        assert image.format == "JPEG"


def test_original_mode_keeps_source_image_pixels_and_uses_lossless_webp(tmp_path: Path) -> None:
    source = tmp_path / "原始图片.png"
    Image.new("RGBA", (317, 193), (20, 80, 160, 128)).save(source, dpi=(144, 144))
    model = DocumentModel()
    model.add_files([source])

    result = export_page_images([model.pages[0]], tmp_path / "输出", "原图", "WebP", None, 20)

    with Image.open(result["outputs"][0]) as image:
        assert image.size == (317, 193)
        assert image.mode == "RGBA"


def test_original_png_never_upscales_and_uses_lossless_compression(tmp_path: Path) -> None:
    source = tmp_path / "大图.png"
    Image.new("RGB", (1200, 800), (24, 80, 160)).save(source)
    model = DocumentModel()
    model.add_files([source])

    result = export_page_images([model.pages[0]], tmp_path / "输出", "原图", "PNG", None)

    output = result["outputs"][0]
    with Image.open(output) as image:
        assert image.size == (1200, 800)
        assert image.getpixel((600, 400)) == (24, 80, 160)
    assert output.stat().st_size < 1200 * 800 * 3


def test_merge_long_image_outputs_one_vertical_image_without_upscaling(tmp_path: Path) -> None:
    first = tmp_path / "第一张.png"
    second = tmp_path / "第二张.png"
    Image.new("RGB", (80, 40), "red").save(first)
    Image.new("RGB", (50, 30), "blue").save(second)
    model = DocumentModel()
    model.add_files([first, second])

    result = export_page_images(
        model.pages,
        tmp_path / "长图输出",
        "组合",
        "PNG",
        None,
        merge_long_image=True,
    )

    assert len(result["outputs"]) == 1
    assert result["exported_pages"] == 2
    assert result["merged"] is True
    with Image.open(result["outputs"][0]) as image:
        assert image.size == (80, 70)
        assert image.getpixel((40, 20))[:3] == (255, 0, 0)
        assert image.getpixel((40, 55))[:3] == (0, 0, 255)


def test_original_mode_renders_pdf_at_highest_quality_600_dpi(tmp_path: Path) -> None:
    source = tmp_path / "source.pdf"
    make_pdf(source)
    model = DocumentModel()
    model.add_files([source])

    result = export_page_images([model.pages[0]], tmp_path / "output", "page", "PNG", None)

    with Image.open(result["outputs"][0]) as image:
        assert image.size == (1200, 600)
