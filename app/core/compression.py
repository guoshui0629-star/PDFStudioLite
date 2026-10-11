from __future__ import annotations

import io
import os
import shutil
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import pikepdf
import pymupdf
from PIL import Image

from app.core.models import CompressionResult
from app.core.pdf_engine import CancelledError


TARGET_MAX_ERROR_BYTES = 512 * 1024
MAX_SEARCH_ROUNDS = 96


@dataclass(frozen=True, slots=True)
class _Candidate:
    path: Path
    size: int
    quality: int
    max_dimension: int | None
    image_limit: int | None
    boost_quality: int | None = None
    boost_count: int = 0

    def label(self) -> str:
        dimension = "原始尺寸" if self.max_dimension is None else f"最长边 {self.max_dimension}px"
        scope = "全部图片" if self.image_limit is None else f"压缩 {self.image_limit} 张图片"
        refinement = f" · {self.boost_count} 张质量 {self.boost_quality}" if self.boost_quality is not None else ""
        return f"{dimension} · {scope} · 质量 {self.quality}{refinement}"


def lossless_optimize(source: str | Path, destination: str | Path) -> CompressionResult:
    source_path = Path(source).resolve()
    output_path = Path(destination).resolve()
    if source_path == output_path:
        raise ValueError("无损优化必须另存为新文件。")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with pikepdf.open(source_path) as pdf:
        pdf.save(
            output_path,
            compress_streams=True,
            recompress_flate=True,
            object_stream_mode=pikepdf.ObjectStreamMode.generate,
        )
    size = output_path.stat().st_size
    return CompressionResult(output_path, source_path.stat().st_size, size, None, True, "lossless", "无损优化完成。")


def _compressed_candidate(
    source: Path,
    destination: Path,
    quality: int,
    max_dimension: int | None,
    image_limit: int | None = None,
    boost_quality: int | None = None,
    boost_count: int = 0,
) -> None:
    shutil.copy2(source, destination)
    doc = pymupdf.open(destination)
    try:
        inventory: dict[int, tuple[int, bytes, int]] = {}
        for page_number, page in enumerate(doc):
            for info in page.get_images(full=True):
                xref = info[0]
                if xref in inventory:
                    continue
                extracted = doc.extract_image(xref)
                raw = extracted.get("image")
                if not raw:
                    continue
                inventory[xref] = (len(raw), raw, page_number)
        ordered = sorted(inventory.items(), key=lambda item: item[1][0], reverse=True)
        if image_limit is not None:
            ordered = ordered[:image_limit]
        for position, (xref, (_, raw, page_number)) in enumerate(ordered):
            try:
                with Image.open(io.BytesIO(raw)) as image:
                    has_alpha = image.mode in {"RGBA", "LA"} or "transparency" in image.info
                    if has_alpha:
                        continue
                    image = image.convert("RGB")
                    if max_dimension is not None and max(image.size) > max_dimension:
                        image.thumbnail((max_dimension, max_dimension), Image.Resampling.LANCZOS)
                    stream = io.BytesIO()
                    selected_quality = boost_quality if boost_quality is not None and position < boost_count else quality
                    image.save(stream, "JPEG", quality=selected_quality, optimize=True, progressive=True)
                    doc[page_number].replace_image(xref, stream=stream.getvalue())
            except Exception:
                continue
        temp = destination.with_suffix(".rewrite.pdf")
        doc.save(temp, garbage=4, deflate=True, use_objstms=1)
        doc.close()
        os.replace(temp, destination)
    finally:
        if not doc.is_closed:
            doc.close()


def _image_max_dimension(source: Path) -> int:
    maximum = 0
    with pymupdf.open(source) as doc:
        seen: set[int] = set()
        for page in doc:
            for info in page.get_images(full=True):
                xref, width, height = info[0], info[2], info[3]
                if xref not in seen:
                    maximum = max(maximum, width, height)
                    seen.add(xref)
    return maximum


def _image_count(source: Path) -> int:
    with pymupdf.open(source) as doc:
        return len({info[0] for page in doc for info in page.get_images(full=True)})


def compress_to_target(
    source: str | Path,
    destination: str | Path,
    target_bytes: int,
    progress: Callable[[int, int, str], None] | None = None,
    cancelled: Callable[[], bool] | None = None,
) -> CompressionResult:
    source_path = Path(source).resolve()
    output_path = Path(destination).resolve()
    if source_path == output_path:
        raise ValueError("压缩结果必须另存为新文件。")
    if target_bytes <= 0:
        raise ValueError("目标大小必须大于 0。")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    original_size = source_path.stat().st_size

    with tempfile.TemporaryDirectory(prefix="pdf-studio-compress-") as folder:
        work = Path(folder)
        lossless_path = work / "lossless.pdf"
        lossless = lossless_optimize(source_path, lossless_path)
        lower_bound = max(0, target_bytes - TARGET_MAX_ERROR_BYTES)

        def acceptable(size: int) -> bool:
            return lower_bound <= size <= target_bytes
        if lossless.output_bytes <= target_bytes:
            shutil.copy2(lossless_path, output_path)
            within = lossless.output_bytes >= lower_bound
            message = "仅通过无损优化已在目标误差 0.5 MB 内。" if within else "文件已经小于目标值；未添加无意义填充数据。"
            return CompressionResult(output_path, original_size, output_path.stat().st_size, target_bytes, within, "target", message)

        source_max = _image_max_dimension(lossless_path)
        dimension_steps: list[int | None] = [None]
        for dimension in (4096, 3584, 3200, 2816, 2560, 2304, 2048, 1792, 1536, 1280, 1024, 800, 640):
            if source_max > dimension:
                dimension_steps.append(dimension)

        candidates: list[_Candidate] = []
        attempts = 0

        def generate(
            dimension: int | None,
            quality: int,
            image_limit: int | None = None,
            boost_quality: int | None = None,
            boost_count: int = 0,
        ) -> _Candidate:
            nonlocal attempts
            if cancelled and cancelled():
                raise CancelledError("压缩已取消。")
            attempts += 1
            dimension_name = "original" if dimension is None else str(dimension)
            limit_name = "all" if image_limit is None else str(image_limit)
            boost_name = "none" if boost_quality is None else f"{boost_quality}-{boost_count}"
            candidate_path = work / f"candidate-{dimension_name}-{limit_name}-{quality}-{boost_name}.pdf"
            _compressed_candidate(
                lossless_path,
                candidate_path,
                quality,
                dimension,
                image_limit,
                boost_quality,
                boost_count,
            )
            candidate = _Candidate(
                candidate_path,
                candidate_path.stat().st_size,
                quality,
                dimension,
                image_limit,
                boost_quality,
                boost_count,
            )
            candidates.append(candidate)
            if progress:
                progress(
                    attempts,
                    MAX_SEARCH_ROUNDS,
                    f"第 {attempts} 轮 · {candidate.label()} · {candidate.size / (1024 * 1024):.2f} MB",
                )
            return candidate

        image_count = _image_count(lossless_path)

        # For each resolution, use an actual-output binary search to find the
        # highest JPEG quality that does not exceed the requested size.
        for dimension in dimension_steps:
            if attempts >= MAX_SEARCH_ROUNDS:
                break
            high_candidate = generate(dimension, 100)
            if acceptable(high_candidate.size):
                break
            if high_candidate.size < lower_bound:
                # Re-encoding every image can create a large size gap even at
                # quality 100. Search how many of the largest images should be
                # re-encoded, then refine quality at the boundary.
                low_count, high_count = 1, image_count
                boundary_counts: set[int] = set()
                while low_count <= high_count and attempts < MAX_SEARCH_ROUNDS:
                    count = (low_count + high_count) // 2
                    candidate = generate(dimension, 100, count)
                    boundary_counts.add(count)
                    if acceptable(candidate.size):
                        break
                    if candidate.size > target_bytes:
                        low_count = count + 1
                    else:
                        high_count = count - 1
                for count in range(max(1, high_count - 1), min(image_count, low_count + 1) + 1):
                    if attempts >= MAX_SEARCH_ROUNDS:
                        break
                    boundary_counts.add(count)
                    if not any(c.image_limit == count and c.max_dimension == dimension and c.quality == 100 for c in candidates):
                        generate(dimension, 100, count)
                if any(acceptable(candidate.size) for candidate in candidates):
                    break
                # If one more compressed image crosses the target, vary its
                # JPEG quality to fill the remaining gap.
                for count in sorted(boundary_counts):
                    high = next(
                        (c for c in candidates if c.image_limit == count and c.max_dimension == dimension and c.quality == 100),
                        None,
                    )
                    if high is None or high.size <= target_bytes:
                        continue
                    low = generate(dimension, 20, count)
                    if low.size > target_bytes:
                        continue
                    q_low, q_high = 21, 99
                    while q_low <= q_high and attempts < MAX_SEARCH_ROUNDS:
                        quality = (q_low + q_high) // 2
                        candidate = generate(dimension, quality, count)
                        if candidate.size > target_bytes:
                            q_high = quality - 1
                        else:
                            q_low = quality + 1
                    if any(acceptable(candidate.size) for candidate in candidates):
                        break
                # Lower resolutions can only move farther below the target.
                break

            low_candidate = generate(dimension, 20)
            if acceptable(low_candidate.size):
                break
            if low_candidate.size > target_bytes:
                # Even aggressive quality reduction is insufficient; continue
                # with a smaller pixel dimension.
                continue

            low_quality, high_quality = 21, 99
            while low_quality <= high_quality and attempts < MAX_SEARCH_ROUNDS:
                quality = (low_quality + high_quality) // 2
                candidate = generate(dimension, quality)
                if acceptable(candidate.size):
                    low_quality = quality + 1
                elif candidate.size > target_bytes:
                    high_quality = quality - 1
                else:
                    low_quality = quality + 1

            # Check the immediate boundary qualities because JPEG size isn't
            # perfectly monotonic for every image set.
            tested = {
                candidate.quality
                for candidate in candidates
                if candidate.max_dimension == dimension and candidate.image_limit is None
            }
            for quality in range(max(20, high_quality - 2), min(100, low_quality + 2) + 1):
                if attempts >= MAX_SEARCH_ROUNDS:
                    break
                if quality not in tested:
                    generate(dimension, quality)

            if any(acceptable(candidate.size) for candidate in candidates):
                break

        # Refine the final quality boundary one image at a time. Changing the
        # quality of every image together can jump by several megabytes; this
        # distributes that jump across individual resources.
        under_target = [candidate for candidate in candidates if candidate.size <= target_bytes]
        if under_target and not acceptable(max(under_target, key=lambda candidate: candidate.size).size):
            configurations = {(candidate.max_dimension, candidate.image_limit) for candidate in candidates}
            for dimension, limit in configurations:
                if attempts >= MAX_SEARCH_ROUNDS:
                    break
                group = [
                    candidate
                    for candidate in candidates
                    if candidate.max_dimension == dimension
                    and candidate.image_limit == limit
                    and candidate.boost_quality is None
                ]
                lows = [candidate for candidate in group if candidate.size <= target_bytes]
                highs = [candidate for candidate in group if candidate.size > target_bytes]
                pairs = [
                    (low, high)
                    for low in lows
                    for high in highs
                    if high.quality > low.quality
                ]
                if not pairs:
                    continue
                low, high = min(
                    pairs,
                    key=lambda pair: (
                        pair[1].quality - pair[0].quality,
                        target_bytes - pair[0].size,
                        pair[1].size - target_bytes,
                    ),
                )
                count = limit if limit is not None else image_count
                if count <= 1:
                    continue
                boost_low, boost_high = 1, count - 1
                while boost_low <= boost_high and attempts < MAX_SEARCH_ROUNDS:
                    boost_count = (boost_low + boost_high) // 2
                    candidate = generate(dimension, low.quality, limit, high.quality, boost_count)
                    if acceptable(candidate.size):
                        break
                    if candidate.size > target_bytes:
                        boost_high = boost_count - 1
                    else:
                        boost_low = boost_count + 1
                if any(acceptable(candidate.size) for candidate in candidates):
                    break

        under_target = [candidate for candidate in candidates if candidate.size <= target_bytes]
        if under_target:
            best = max(under_target, key=lambda candidate: candidate.size)
        elif candidates:
            best = min(candidates, key=lambda candidate: candidate.size)
        else:
            best = _Candidate(lossless_path, lossless.output_bytes, 100, None, None)

        shutil.copy2(best.path, output_path)
        output_size = output_path.stat().st_size
        within_tolerance = acceptable(output_size)
        if within_tolerance:
            error_bytes = target_bytes - output_size
            message = f"已达到目标，误差 {error_bytes / (1024 * 1024):.2f} MB。"
        elif output_size <= target_bytes:
            error_bytes = target_bytes - output_size
            message = f"未能进入 0.5 MB 误差范围；当前结果低于目标 {error_bytes / (1024 * 1024):.2f} MB。"
        else:
            message = "在保留文字和矢量内容的前提下无法压到目标大小。"
        return CompressionResult(output_path, original_size, output_size, target_bytes, within_tolerance, "target", message)
