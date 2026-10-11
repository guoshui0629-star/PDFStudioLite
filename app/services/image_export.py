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


def unique_output_path(folder: Path, stem: str, suffix: str) -> Path:
    candidate = folder / f"{stem}{suffix}"
    counter = 2
    while candidate.exists():
        candidate = folder / f"{stem}_{counter}{suffix}"
        counter += 1
    return candidate


def export_page_images(
    pages: Sequence[PageRef],
    output_dir: str | Path,
    prefix: str,
    image_format: str,
    dpi: int | None,
    quality: int = 90,
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
    for number, page_ref in enumerate(pages, start=1):
        if cancelled and cancelled():
            raise CancelledError("图片导出已取消。")
        destination = unique_output_path(folder, f"{prefix}{number}", suffix)
        try:
            if page_ref.kind == SourceKind.PDF:
                with pymupdf.open(page_ref.source) as doc:
                    page = doc[page_ref.source_page]
                    matrix = pymupdf.Matrix(render_dpi / 72.0, render_dpi / 72.0)
                    if page_ref.rotation:
                        matrix = matrix.prerotate(page_ref.rotation)
                    pix = page.get_pixmap(matrix=matrix, alpha=format_name in {"PNG", "WEBP"})
                    mode = "RGBA" if pix.alpha else "RGB"
                    image = Image.frombytes(mode, (pix.width, pix.height), pix.samples)
            else:
                with Image.open(page_ref.source) as source:
                    source_dpi = source.info.get("dpi")
                    image = ImageOps.exif_transpose(source).copy()
                if page_ref.rotation:
                    image = image.rotate(-page_ref.rotation, expand=True)
            if format_name == "JPG":
                image = image.convert("RGB")
            fd, temp_name = tempfile.mkstemp(prefix=".pdfstudio-image-", suffix=suffix, dir=folder)
            os.close(fd)
            temp = Path(temp_name)
            save_options: dict[str, object] = {}
            if page_ref.kind == SourceKind.PDF:
                save_options["dpi"] = (render_dpi, render_dpi)
            elif original_mode and source_dpi:
                save_options["dpi"] = source_dpi
            elif not original_mode:
                save_options["dpi"] = (render_dpi, render_dpi)
            if format_name == "JPG":
                save_options["quality"] = 100 if original_mode else quality
                if original_mode:
                    save_options["subsampling"] = 0
            elif format_name == "WEBP":
                save_options["quality"] = 100 if original_mode else quality
                if original_mode:
                    save_options["lossless"] = True
            elif format_name == "PNG":
                save_options["compress_level"] = 0 if original_mode else 6
                save_options["optimize"] = not original_mode
            elif format_name == "TIFF" and not original_mode:
                save_options["compression"] = "tiff_lzw"
            image.save(temp, format=format_name if format_name != "JPG" else "JPEG", **save_options)
            os.replace(temp, destination)
            outputs.append(destination)
        except Exception as error:
            failures.append(f"{page_ref.source.name}：{error}")
        if progress:
            progress(number, len(pages), f"正在导出 {number} / {len(pages)} 页")
    return {"outputs": outputs, "failures": failures, "output_dir": folder}
