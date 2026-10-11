from __future__ import annotations

import base64
import json
import os
import re
import tempfile
from math import ceil
from collections import defaultdict
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pymupdf

from app.core.pdf_engine import CancelledError


MARKER_PREFIX = b"%PDFStudioLite-Watermark:"
MARKER_PATTERN = re.compile(rb"^%PDFStudioLite-Watermark:([A-Za-z0-9_-]+)")


@dataclass(frozen=True, slots=True)
class WatermarkSpec:
    kind: str = "text"
    label: str = "PDF Studio Lite 水印"
    text: str = "仅供内部使用"
    font_family: str = "Microsoft YaHei UI"
    font_size: float = 48.0
    color: str = "#B0B0B0"
    opacity: float = 0.25
    rotation: float = -45.0
    bold: bool = False
    italic: bool = False
    position: str = "center"
    tiled: bool = False
    horizontal_gap: float = 72.0
    vertical_gap: float = 72.0
    scale_percent: float = 28.0
    overlay: bool = True


@dataclass(frozen=True, slots=True)
class WatermarkAsset:
    png: bytes
    width_points: float
    height_points: float


@dataclass(frozen=True, slots=True)
class WatermarkRecord:
    watermark_id: str
    label: str
    kind: str
    pages: tuple[int, ...]
    stream_count: int
    removable: bool
    reason: str
    source: str = "pdf-studio-lite"


def parse_page_range(expression: str, page_count: int) -> tuple[int, ...]:
    """Parse a human one-based range such as ``1-5,8,10-12``."""
    text = expression.strip().replace("，", ",")
    if not text:
        raise ValueError("请输入页码范围。")
    pages: set[int] = set()
    for token in text.split(","):
        part = token.strip()
        if not part:
            raise ValueError("页码范围中存在空白项目。")
        if "-" in part:
            bounds = part.split("-")
            if len(bounds) != 2 or not all(value.strip().isdigit() for value in bounds):
                raise ValueError(f"页码范围格式错误：{part}")
            start, end = (int(value) for value in bounds)
            if start > end:
                raise ValueError(f"页码范围起始值不能大于结束值：{part}")
            pages.update(range(start, end + 1))
        elif part.isdigit():
            pages.add(int(part))
        else:
            raise ValueError(f"页码格式错误：{part}")
    if not pages or min(pages) < 1 or max(pages) > page_count:
        raise ValueError(f"页码必须位于 1 到 {page_count} 之间。")
    return tuple(page - 1 for page in sorted(pages))


def _marker(metadata: dict[str, object]) -> bytes:
    payload = json.dumps(metadata, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return MARKER_PREFIX + base64.urlsafe_b64encode(payload).rstrip(b"=") + b"\n"


def _decode_marker(stream: bytes) -> dict[str, object] | None:
    match = MARKER_PATTERN.match(stream)
    if not match:
        return None
    encoded = match.group(1)
    encoded += b"=" * (-len(encoded) % 4)
    try:
        value = json.loads(base64.urlsafe_b64decode(encoded).decode("utf-8"))
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _single_rect(page_rect: pymupdf.Rect, width: float, height: float, position: str) -> pymupdf.Rect:
    margin = min(page_rect.width, page_rect.height) * 0.05
    columns = {
        "left": page_rect.x0 + margin,
        "center": page_rect.x0 + (page_rect.width - width) / 2,
        "right": page_rect.x1 - margin - width,
    }
    rows = {
        "top": page_rect.y0 + margin,
        "middle": page_rect.y0 + (page_rect.height - height) / 2,
        "bottom": page_rect.y1 - margin - height,
    }
    vertical, horizontal = {
        "top-left": ("top", "left"),
        "top-center": ("top", "center"),
        "top-right": ("top", "right"),
        "middle-left": ("middle", "left"),
        "center": ("middle", "center"),
        "middle-right": ("middle", "right"),
        "bottom-left": ("bottom", "left"),
        "bottom-center": ("bottom", "center"),
        "bottom-right": ("bottom", "right"),
    }.get(position, ("middle", "center"))
    x0, y0 = columns[horizontal], rows[vertical]
    return pymupdf.Rect(x0, y0, x0 + width, y0 + height)


def _placement_rects(page_rect: pymupdf.Rect, asset: WatermarkAsset, spec: WatermarkSpec) -> list[pymupdf.Rect]:
    width, height = asset.width_points, asset.height_points
    if spec.kind == "image":
        requested = page_rect.width * max(0.01, min(spec.scale_percent, 100.0)) / 100.0
        factor = requested / max(width, 1.0)
        width, height = requested, height * factor
    max_width, max_height = page_rect.width * 0.9, page_rect.height * 0.9
    factor = min(max_width / max(width, 1.0), max_height / max(height, 1.0), 1.0)
    width, height = width * factor, height * factor
    if not spec.tiled:
        return [_single_rect(page_rect, width, height, spec.position)]
    rects: list[pymupdf.Rect] = []
    x_step = max(width + spec.horizontal_gap, 1.0)
    y_step = max(height + spec.vertical_gap, 1.0)
    y = page_rect.y0 + spec.vertical_gap / 2
    row = 0
    while y + height <= page_rect.y1:
        x = page_rect.x0 + spec.horizontal_gap / 2 - (x_step / 2 if row % 2 else 0)
        while x < page_rect.x1:
            if x + width > page_rect.x0 and x < page_rect.x1:
                rects.append(pymupdf.Rect(x, y, x + width, y + height))
            x += x_step
        y += y_step
        row += 1
    return rects


def apply_watermark(
    input_path: str | Path,
    output_path: str | Path,
    asset: WatermarkAsset,
    spec: WatermarkSpec,
    page_indices: Iterable[int],
    *,
    progress: Callable[[int, int, str], None] | None = None,
    cancelled: Callable[[], bool] | None = None,
) -> WatermarkRecord:
    source = Path(input_path).resolve()
    destination = Path(output_path).resolve()
    if source == destination:
        raise ValueError("水印输出不能覆盖原始 PDF。")
    destination.parent.mkdir(parents=True, exist_ok=True)
    selected = tuple(sorted(set(page_indices)))
    watermark_id = uuid4().hex
    created = datetime.now(UTC).isoformat()
    fd, temp_name = tempfile.mkstemp(prefix=".pdfstudio-watermark-", suffix=".pdf", dir=destination.parent)
    os.close(fd)
    temp = Path(temp_name)
    document = pymupdf.open(source)
    try:
        if document.needs_pass:
            raise ValueError("PDF 已加密，需要先解密后再添加水印。")
        if not selected:
            raise ValueError("没有选择需要添加水印的页面。")
        if selected[0] < 0 or selected[-1] >= document.page_count:
            raise ValueError("水印页码超出文档范围。")
        total_streams = 0
        for current, page_number in enumerate(selected, start=1):
            if cancelled and cancelled():
                raise CancelledError("水印任务已取消。")
            page = document[page_number]
            for instance, rect in enumerate(_placement_rects(page.rect, asset, spec), start=1):
                before = set(page.get_contents())
                page.insert_image(rect, stream=asset.png, keep_proportion=True, overlay=spec.overlay)
                created_streams = set(page.get_contents()) - before
                if not created_streams:
                    raise RuntimeError("无法隔离新建的水印内容流。")
                metadata = {
                    "schema": 1,
                    "id": watermark_id,
                    "label": spec.label,
                    "kind": spec.kind,
                    "created": created,
                    "page": page_number,
                    "instance": instance,
                    "spec": asdict(spec),
                }
                for xref in created_streams:
                    stream = document.xref_stream(xref)
                    document.update_stream(xref, _marker(metadata) + stream)
                    total_streams += 1
            if progress:
                progress(current, len(selected), f"正在添加水印 {current} / {len(selected)} 页")
        document.save(temp, garbage=4, deflate=True, use_objstms=1)
        document.close()
        check = scan_watermarks(temp)
        record = next((item for item in check if item.watermark_id == watermark_id), None)
        if record is None or record.stream_count != total_streams:
            raise RuntimeError("水印标识校验失败，未写入输出文件。")
        os.replace(temp, destination)
        return record
    finally:
        if not document.is_closed:
            document.close()
        temp.unlink(missing_ok=True)


def scan_watermarks(path: str | Path) -> list[WatermarkRecord]:
    groups: dict[str, dict[str, object]] = {}
    annotation_records: list[WatermarkRecord] = []
    repeated_text: dict[tuple[str, int, int], set[int]] = defaultdict(set)
    repeated_images: dict[int, set[int]] = defaultdict(set)
    owned_image_xrefs: set[int] = set()
    with pymupdf.open(path) as document:
        if document.needs_pass:
            raise ValueError("PDF 已加密，无法检测水印。")
        for page_number, page in enumerate(document):
            owned_resource_names: set[str] = set()
            for xref in page.get_contents():
                content_stream = document.xref_stream(xref)
                metadata = _decode_marker(content_stream)
                if not metadata or metadata.get("schema") != 1 or not isinstance(metadata.get("id"), str):
                    continue
                owned_resource_names.update(
                    match.decode("ascii", errors="ignore")
                    for match in re.findall(rb"/([^\s/]+)\s+Do", content_stream)
                )
                watermark_id = str(metadata["id"])
                group = groups.setdefault(
                    watermark_id,
                    {
                        "label": str(metadata.get("label") or "PDF Studio Lite 水印"),
                        "kind": str(metadata.get("kind") or "unknown"),
                        "pages": set(),
                        "streams": 0,
                    },
                )
                group["pages"].add(page_number + 1)  # type: ignore[union-attr]
                group["streams"] = int(group["streams"]) + 1
            annotations = list(page.annots(types=[pymupdf.PDF_ANNOT_WATERMARK]) or [])
            for annotation in annotations:
                annotation_id = annotation.info.get("id") or f"xref-{annotation.xref}"
                annotation_records.append(
                    WatermarkRecord(
                        watermark_id=f"annotation:{annotation_id}",
                        label=annotation.info.get("subject") or annotation.info.get("content") or "独立 Watermark Annotation",
                        kind="annotation",
                        pages=(page_number + 1,),
                        stream_count=1,
                        removable=True,
                        reason="PDF /Watermark 独立注释对象，可在不修改正文内容流的情况下删除。",
                        source="watermark-annotation",
                    )
                )
            text_data = page.get_text("dict")
            for block in text_data.get("blocks", []):
                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        text = " ".join(str(span.get("text", "")).split())
                        bbox = span.get("bbox")
                        if len(text) < 3 or not bbox:
                            continue
                        x_bin = round(float(bbox[0]) / max(page.rect.width, 1) * 10)
                        y_bin = round(float(bbox[1]) / max(page.rect.height, 1) * 10)
                        repeated_text[(text, x_bin, y_bin)].add(page_number + 1)
            for image in page.get_images(full=True):
                image_xref = int(image[0])
                resource_name = str(image[7]) if len(image) > 7 else ""
                if resource_name in owned_resource_names:
                    owned_image_xrefs.add(image_xref)
            for image_info in page.get_image_info(xrefs=True):
                image_xref = int(image_info.get("xref", 0))
                if image_xref > 0:
                    repeated_images[image_xref].add(page_number + 1)
        page_count = document.page_count
    own_records = [
        WatermarkRecord(
            watermark_id=watermark_id,
            label=str(group["label"]),
            kind=str(group["kind"]),
            pages=tuple(sorted(group["pages"])),  # type: ignore[arg-type]
            stream_count=int(group["streams"]),
            removable=True,
            reason="包含 PDF Studio Lite 可追踪标识，可精确移除独立内容流。",
        )
        for watermark_id, group in groups.items()
    ]
    threshold = max(2, ceil(page_count * 0.5))
    suspected_text_records = [
        WatermarkRecord(
            watermark_id=f"suspected-text:{abs(hash(signature))}",
            label=f"疑似重复文字：{signature[0][:32]}",
            kind="text",
            pages=tuple(sorted(pages)),
            stream_count=len(pages),
            removable=False,
            reason="相同文字在多页相近位置重复出现，但无法证明它与正文内容流分离，因此仅检测、不删除。",
            source="suspected-text",
        )
        for signature, pages in repeated_text.items()
        if len(pages) >= threshold
    ]
    suspected_image_records = [
        WatermarkRecord(
            watermark_id=f"suspected-image:{xref}",
            label=f"疑似重复图片对象 xref {xref}",
            kind="image",
            pages=tuple(sorted(pages)),
            stream_count=len(pages),
            removable=False,
            reason="同一图片资源在多页重复引用，可能是 Logo 或正常内容；无法安全删除对应绘制引用。",
            source="suspected-image",
        )
        for xref, pages in repeated_images.items()
        if len(pages) >= threshold and xref not in owned_image_xrefs
    ]
    return own_records + annotation_records + suspected_text_records + suspected_image_records


def remove_watermarks(
    input_path: str | Path,
    output_path: str | Path,
    watermark_ids: Iterable[str],
    *,
    progress: Callable[[int, int, str], None] | None = None,
    cancelled: Callable[[], bool] | None = None,
) -> tuple[WatermarkRecord, ...]:
    source = Path(input_path).resolve()
    destination = Path(output_path).resolve()
    if source == destination:
        raise ValueError("去水印输出不能覆盖原始 PDF。")
    selected = set(watermark_ids)
    available = {record.watermark_id: record for record in scan_watermarks(source)}
    unknown = selected - available.keys()
    if unknown:
        raise ValueError("选中的水印标识不存在或已被移除。")
    if not selected:
        raise ValueError("没有选择需要移除的水印。")
    unsafe = [watermark_id for watermark_id in selected if not available[watermark_id].removable]
    if unsafe:
        raise ValueError("选中项包含无法安全移除的疑似水印。")
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=".pdfstudio-remove-watermark-", suffix=".pdf", dir=destination.parent)
    os.close(fd)
    temp = Path(temp_name)
    document = pymupdf.open(source)
    try:
        total = document.page_count
        for current, page in enumerate(document, start=1):
            if cancelled and cancelled():
                raise CancelledError("移除水印任务已取消。")
            keep: list[int] = []
            changed = False
            for xref in page.get_contents():
                metadata = _decode_marker(document.xref_stream(xref))
                if metadata and metadata.get("id") in selected:
                    changed = True
                else:
                    keep.append(xref)
            if changed:
                contents = "[" + " ".join(f"{xref} 0 R" for xref in keep) + "]"
                document.xref_set_key(page.xref, "Contents", contents)
            for annotation in list(page.annots(types=[pymupdf.PDF_ANNOT_WATERMARK]) or []):
                annotation_id = annotation.info.get("id") or f"xref-{annotation.xref}"
                if f"annotation:{annotation_id}" in selected:
                    page.delete_annot(annotation)
            if progress:
                progress(current, total, f"正在移除水印 {current} / {total} 页")
        document.save(temp, garbage=4, deflate=True, use_objstms=1)
        document.close()
        remaining = {record.watermark_id for record in scan_watermarks(temp)}
        if selected & remaining:
            raise RuntimeError("水印移除校验失败，未写入输出文件。")
        os.replace(temp, destination)
        return tuple(available[watermark_id] for watermark_id in selected)
    finally:
        if not document.is_closed:
            document.close()
        temp.unlink(missing_ok=True)
