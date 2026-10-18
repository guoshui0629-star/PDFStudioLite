from __future__ import annotations

import os
import tempfile
from collections.abc import Callable, Sequence
from pathlib import Path

import pymupdf
from PIL import Image, ImageOps

from app.core.models import PageRef, SourceKind
from app.core.pdf_engine import CancelledError

PDF_HIGHEST_QUALITY_DPI = 600
WEBP_MAX_DIMENSION = 16_383
JPEG_MAX_DIMENSION = 65_500


def unique_output_path(folder: Path, stem: str, suffix: str) -> Path:
    candidate = folder / f"{stem}{suffix}"
    counter = 2
    while candidate.exists():
        candidate = folder / f"{stem}_{counter}{suffix}"
        counter += 1
    return candidate


def _render_page_image(
    page_ref: PageRef,
    format_name: str,
    render_dpi: int,
) -> tuple[Image.Image, tuple[float, float] | None]:
    if page_ref.kind == SourceKind.PDF:
        with pymupdf.open(page_ref.source) as doc:
            page = doc[page_ref.source_page]
            matrix = pymupdf.Matrix(render_dpi / 72.0, render_dpi / 72.0)
            if page_ref.rotation:
                matrix = matrix.prerotate(page_ref.rotation)
            pix = page.get_pixmap(matrix=matrix, alpha=format_name in {"PNG", "WEBP", "TIFF"})
            mode = "RGBA" if pix.alpha else "RGB"
            return Image.frombytes(mode, (pix.width, pix.height), pix.samples), (render_dpi, render_dpi)

    with Image.open(page_ref.source) as source:
        source_dpi = source.info.get("dpi")
        image = ImageOps.exif_transpose(source).copy()
    if page_ref.rotation:
        image = image.rotate(-page_ref.rotation, expand=True)
    return image, source_dpi


def _validate_format_dimensions(format_name: str, size: tuple[int, int]) -> None:
    width, height = size
    if format_name == "WEBP" and max(width, height) > WEBP_MAX_DIMENSION:
        raise ValueError(f"WebP 单边最大支持 {WEBP_MAX_DIMENSION} 像素，请改用 PNG 或 TIFF。")
    if format_name == "JPG" and max(width, height) > JPEG_MAX_DIMENSION:
        raise ValueError(f"JPG 单边最大支持 {JPEG_MAX_DIMENSION} 像素，请改用 PNG 或 TIFF。")


def _save_image(
    image: Image.Image,
    destination: Path,
    format_name: str,
    original_mode: bool,
    quality: int,
    output_dpi: tuple[float, float] | None,
) -> None:
    _validate_format_dimensions(format_name, image.size)
    if format_name == "JPG" and image.mode != "RGB":
        background = Image.new("RGB", image.size, "white")
        if "A" in image.getbands():
            background.paste(image, mask=image.getchannel("A"))
        else:
            background.paste(image)
        image = background
    fd, temp_name = tempfile.mkstemp(prefix=".pdfstudio-image-", suffix=destination.suffix, dir=destination.parent)
    os.close(fd)
    temp = Path(temp_name)
    save_options: dict[str, object] = {}
    if output_dpi:
        save_options["dpi"] = output_dpi
    if format_name == "JPG":
        save_options["quality"] = 100 if original_mode else quality
        if original_mode:
            save_options["subsampling"] = 0
    elif format_name == "WEBP":
        save_options["quality"] = 100 if original_mode else quality
        save_options["lossless"] = original_mode
    elif format_name == "PNG":
        # PNG compression is always pixel-lossless. Level 6 avoids the enormous
        # uncompressed files previously produced by original-quality mode.
        save_options["compress_level"] = 6
        save_options["optimize"] = original_mode
    elif format_name == "TIFF":
        save_options["compression"] = "tiff_lzw"
    try:
        image.save(temp, format=format_name if format_name != "JPG" else "JPEG", **save_options)
        os.replace(temp, destination)
    finally:
        temp.unlink(missing_ok=True)


def export_page_images(
    pages: Sequence[PageRef],
    output_dir: str | Path,
    prefix: str,
    image_format: str,
    dpi: int | None,
    quality: int = 90,
    merge_long_image: bool = False,
    progress: Callable[[int, int, str], None] | None = None,
    cancelled: Callable[[], bool] | None = None,
) -> dict[str, object]:
    folder = Path(output_dir)
    folder.mkdir(parents=True, exist_ok=True)
    format_name = image_format.upper()
    original_mode = dpi is None
    render_dpi = PDF_HIGHEST_QUALITY_DPI if original_mode else dpi
    suffix = {"JPG": ".jpg", "PNG": ".png", "WEBP": ".webp", "TIFF": ".tiff"}[format_name]
    outputs: list[Path] = []
    failures: list[str] = []
    rendered: list[tuple[Image.Image, tuple[float, float] | None]] = []
    for number, page_ref in enumerate(pages, start=1):
        if cancelled and cancelled():
            raise CancelledError("图片导出已取消。")
        try:
            image, source_dpi = _render_page_image(page_ref, format_name, render_dpi)
            output_dpi = source_dpi if original_mode and source_dpi else (render_dpi, render_dpi)
            if merge_long_image:
                rendered.append((image, output_dpi))
            else:
                destination = unique_output_path(folder, f"{prefix}{number}", suffix)
                _save_image(image, destination, format_name, original_mode, quality, output_dpi)
                image.close()
                outputs.append(destination)
        except Exception as error:
            failures.append(f"{page_ref.source.name}：{error}")
        if progress:
            action = "正在准备长图" if merge_long_image else "正在导出"
            progress(number, len(pages), f"{action} {number} / {len(pages)} 页")

    exported_pages = len(pages) - len(failures)
    if merge_long_image and rendered:
        destination = unique_output_path(folder, f"{prefix}长图", suffix)
        width = max(image.width for image, _ in rendered)
        height = sum(image.height for image, _ in rendered)
        _validate_format_dimensions(format_name, (width, height))
        has_alpha = format_name != "JPG" and any("A" in image.getbands() for image, _ in rendered)
        canvas = Image.new("RGBA" if has_alpha else "RGB", (width, height), (255, 255, 255, 0) if has_alpha else "white")
        y = 0
        try:
            for image, _ in rendered:
                x = (width - image.width) // 2
                # Direct RGBA paste preserves the source alpha values exactly;
                # using the image again as a mask would multiply alpha twice.
                canvas.paste(image, (x, y))
                y += image.height
            merged_dpi = rendered[0][1]
            _save_image(canvas, destination, format_name, original_mode, quality, merged_dpi)
            outputs.append(destination)
        finally:
            canvas.close()
            for image, _ in rendered:
                image.close()
    return {
        "outputs": outputs,
        "failures": failures,
        "output_dir": folder,
        "exported_pages": exported_pages,
        "merged": merge_long_image,
    }
