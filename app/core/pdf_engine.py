from __future__ import annotations

import os
import tempfile
from collections.abc import Callable, Sequence
from pathlib import Path

import pymupdf
from PIL import Image, ImageOps

from app.core.models import ImageLayout, PageRef, PdfFeatureReport, SourceKind


class CancelledError(RuntimeError):
    pass


def inspect_pdf(path: str | Path) -> PdfFeatureReport:
    with pymupdf.open(path) as doc:
        encrypted = bool(doc.needs_pass)
        if encrypted:
            return PdfFeatureReport(encrypted=True)
        has_links = any(page.get_links() for page in doc)
        has_annotations = any(page.first_annot is not None for page in doc)
        has_forms = any(page.first_widget is not None for page in doc)
        has_signatures = False
        for page in doc:
            widget = page.first_widget
            while widget:
                if widget.field_type == pymupdf.PDF_WIDGET_TYPE_SIGNATURE:
                    has_signatures = True
                    break
                widget = widget.next
        try:
            attachments = bool(doc.embfile_names())
        except Exception:
            attachments = False
        return PdfFeatureReport(
            encrypted=False,
            has_bookmarks=bool(doc.get_toc(simple=True)),
            has_links=has_links,
            has_forms=has_forms,
            has_annotations=has_annotations,
            has_attachments=attachments,
            has_signatures=has_signatures,
        )


def _image_page(page_ref: PageRef) -> pymupdf.Document:
    image_path = page_ref.source
    with Image.open(image_path) as source:
        oriented = ImageOps.exif_transpose(source)
        width_px, height_px = oriented.size
        dpi = source.info.get("dpi", (72, 72))
        dpi_x = float(dpi[0] or 72)
        dpi_y = float(dpi[1] or 72)

    width_pt = max(1.0, width_px * 72.0 / dpi_x)
    height_pt = max(1.0, height_px * 72.0 / dpi_y)
    if page_ref.image_layout == ImageLayout.A4:
        page_w, page_h = (595.276, 841.89)
    elif page_ref.image_layout == ImageLayout.FIT:
        scale = min(595.276 / width_pt, 841.89 / height_pt, 1.0)
        page_w, page_h = width_pt * scale, height_pt * scale
    else:
        page_w, page_h = width_pt, height_pt

    doc = pymupdf.open()
    page = doc.new_page(width=page_w, height=page_h)
    target = pymupdf.Rect(0, 0, page_w, page_h)
    if page_ref.image_layout == ImageLayout.A4:
        scale = min(page_w / width_pt, page_h / height_pt)
        target_w, target_h = width_pt * scale, height_pt * scale
        target = pymupdf.Rect(
            (page_w - target_w) / 2,
            (page_h - target_h) / 2,
            (page_w + target_w) / 2,
            (page_h + target_h) / 2,
        )
    # PyMuPDF directly embeds JPEG streams where possible; alpha-capable formats remain lossless.
    page.insert_image(target, filename=str(image_path), keep_proportion=True)
    if page_ref.rotation:
        page.set_rotation(page_ref.rotation)
    return doc


def export_pages(
    pages: Sequence[PageRef],
    output_path: str | Path,
    progress: Callable[[int, int], None] | None = None,
    cancelled: Callable[[], bool] | None = None,
    page_gap_mm: float = 0.0,
    page_size_mm: tuple[float, float] | None = None,
    page_orientation: str = "auto",
    fill_page: bool = False,
) -> Path:
    if not pages:
        raise ValueError("没有可导出的页面。")
    destination = Path(output_path).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    source_paths = {page.source.resolve() for page in pages}
    if destination in source_paths:
        raise ValueError("输出路径不能覆盖任何源文件。")

    fd, temp_name = tempfile.mkstemp(prefix="pdf-studio-", suffix=".pdf", dir=destination.parent)
    os.close(fd)
    temp_path = Path(temp_name)
    result = pymupdf.open()
    opened: dict[Path, pymupdf.Document] = {}
    try:
        total = len(pages)
        for index, page_ref in enumerate(pages, start=1):
            if cancelled and cancelled():
                raise CancelledError("导出已取消。")
            image_doc: pymupdf.Document | None = None
            if page_ref.kind == SourceKind.PDF:
                source = opened.get(page_ref.source)
                if source is None:
                    source = pymupdf.open(page_ref.source)
                    if source.needs_pass:
                        raise ValueError(f"PDF 已加密，需要密码：{page_ref.source.name}")
                    opened[page_ref.source] = source
                source_page_number = page_ref.source_page
            else:
                image_doc = _image_page(page_ref)
                source = image_doc
                source_page_number = 0
            try:
                if page_size_mm is None:
                    result.insert_pdf(source, from_page=source_page_number, to_page=source_page_number)
                    if page_ref.kind == SourceKind.PDF and page_ref.rotation:
                        result[-1].set_rotation((result[-1].rotation + page_ref.rotation) % 360)
                else:
                    width, height = (value * 72.0 / 25.4 for value in page_size_mm)
                    source_rect = source[source_page_number].rect
                    effective_rotation = page_ref.rotation % 180
                    source_landscape = (source_rect.width > source_rect.height) != (effective_rotation == 90)
                    if page_orientation == "landscape" or (page_orientation == "auto" and source_landscape):
                        width, height = max(width, height), min(width, height)
                    else:
                        width, height = min(width, height), max(width, height)
                    target_page = result.new_page(width=width, height=height)
                    source_w, source_h = source_rect.width, source_rect.height
                    if effective_rotation == 90:
                        source_w, source_h = source_h, source_w
                    scale = max(width / source_w, height / source_h) if fill_page else min(width / source_w, height / source_h)
                    placed_w, placed_h = source_w * scale, source_h * scale
                    target_rect = pymupdf.Rect(
                        (width - placed_w) / 2,
                        (height - placed_h) / 2,
                        (width + placed_w) / 2,
                        (height + placed_h) / 2,
                    )
                    target_page.show_pdf_page(
                        target_rect,
                        source,
                        source_page_number,
                        keep_proportion=True,
                        rotate=page_ref.rotation,
                    )
            finally:
                if image_doc is not None:
                    image_doc.close()
            if page_gap_mm > 0 and index < total:
                gap_points = page_gap_mm * 72.0 / 25.4
                page = result[-1]
                media = page.mediabox
                expanded = pymupdf.Rect(media.x0, media.y0, media.x1, media.y1 + gap_points)
                page.set_mediabox(expanded)
                page.set_cropbox(expanded)
            if progress:
                progress(index, total)
        result.save(temp_path, garbage=3, deflate=True, use_objstms=1)
        result.close()
        result = pymupdf.open(temp_path)
        if result.page_count != total:
            raise RuntimeError("导出页数校验失败。")
        result.close()
        os.replace(temp_path, destination)
        return destination
    finally:
        if not result.is_closed:
            result.close()
        for source in opened.values():
            source.close()
        temp_path.unlink(missing_ok=True)


def render_thumbnail(page_ref: PageRef, max_size: int = 220) -> bytes:
    if page_ref.kind == SourceKind.PDF:
        with pymupdf.open(page_ref.source) as doc:
            page = doc.load_page(page_ref.source_page)
            matrix = pymupdf.Matrix(max_size / max(page.rect.width, page.rect.height), max_size / max(page.rect.width, page.rect.height))
            if page_ref.rotation:
                matrix = matrix.prerotate(page_ref.rotation)
            pix = page.get_pixmap(matrix=matrix, alpha=False)
            return pix.tobytes("png")
    with Image.open(page_ref.source) as source:
        image = ImageOps.exif_transpose(source).convert("RGB")
        if page_ref.rotation:
            image = image.rotate(-page_ref.rotation, expand=True)
        image.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
        import io

        buffer = io.BytesIO()
        image.save(buffer, "PNG", optimize=True)
        return buffer.getvalue()
