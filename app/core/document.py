from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

import pymupdf

from app.core.models import DocumentSnapshot, PageRef, SourceKind


SUPPORTED_IMAGES = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}


class DocumentModel:
    """In-memory page plan. Source files remain read-only until export."""

    def __init__(self, undo_limit: int = 100) -> None:
        self.pages: list[PageRef] = []
        self._undo: list[DocumentSnapshot] = []
        self._redo: list[DocumentSnapshot] = []
        self.undo_limit = undo_limit

    @property
    def can_undo(self) -> bool:
        return bool(self._undo)

    @property
    def can_redo(self) -> bool:
        return bool(self._redo)

    @property
    def estimated_bytes(self) -> int:
        """Estimate current plan size from every selected source page.

        PDF source bytes are apportioned by selected page count; image bytes
        are counted for every occurrence so adding or duplicating an image is
        reflected immediately.
        """
        total = 0
        pdf_counts: dict[Path, int] = {}
        for page in self.pages:
            if page.kind == SourceKind.IMAGE:
                if page.source.exists():
                    total += page.source.stat().st_size
            else:
                pdf_counts[page.source] = pdf_counts.get(page.source, 0) + 1
        for path, selected_pages in pdf_counts.items():
            if not path.exists():
                continue
            try:
                with pymupdf.open(path) as doc:
                    page_count = max(1, doc.page_count)
                total += round(path.stat().st_size * selected_pages / page_count)
            except Exception:
                total += path.stat().st_size
        return total

    def _snapshot(self) -> DocumentSnapshot:
        return DocumentSnapshot(tuple(self.pages))

    def _record(self) -> None:
        self._undo.append(self._snapshot())
        self._undo = self._undo[-self.undo_limit :]
        self._redo.clear()

    def add_files(self, paths: Iterable[str | Path], position: int | None = None) -> list[PageRef]:
        incoming: list[PageRef] = []
        for raw in paths:
            path = Path(raw).resolve()
            suffix = path.suffix.lower()
            if suffix == ".pdf":
                with pymupdf.open(path) as doc:
                    if doc.needs_pass:
                        raise ValueError(f"PDF 已加密，需要密码：{path.name}")
                    incoming.extend(PageRef(path, SourceKind.PDF, page_no) for page_no in range(doc.page_count))
            elif suffix in SUPPORTED_IMAGES:
                incoming.append(PageRef(path, SourceKind.IMAGE))
            else:
                raise ValueError(f"不支持的文件格式：{path.name}")
        if not incoming:
            return []
        self._record()
        index = len(self.pages) if position is None else max(0, min(position, len(self.pages)))
        self.pages[index:index] = incoming
        return incoming

    def delete(self, indices: Iterable[int]) -> list[PageRef]:
        valid = sorted({i for i in indices if 0 <= i < len(self.pages)})
        if not valid:
            return []
        self._record()
        removed = [self.pages[i] for i in valid]
        for index in reversed(valid):
            del self.pages[index]
        return removed

    def duplicate(self, indices: Iterable[int]) -> None:
        valid = sorted({i for i in indices if 0 <= i < len(self.pages)})
        if not valid:
            return
        self._record()
        offset = 0
        for index in valid:
            target = index + 1 + offset
            self.pages.insert(target, self.pages[index + offset].duplicate())
            offset += 1

    def rotate(self, indices: Iterable[int], degrees: int = 90) -> None:
        valid = sorted({i for i in indices if 0 <= i < len(self.pages)})
        if not valid:
            return
        self._record()
        for index in valid:
            self.pages[index] = self.pages[index].rotated(degrees)

    def move(self, source_indices: Iterable[int], destination: int) -> None:
        valid = sorted({i for i in source_indices if 0 <= i < len(self.pages)})
        if not valid:
            return
        self._record()
        moving = [self.pages[i] for i in valid]
        remaining = [page for i, page in enumerate(self.pages) if i not in set(valid)]
        adjusted = destination - sum(1 for i in valid if i < destination)
        adjusted = max(0, min(adjusted, len(remaining)))
        self.pages[:] = remaining[:adjusted] + moving + remaining[adjusted:]

    def move_relative(self, indices: Iterable[int], direction: int) -> None:
        valid = sorted({i for i in indices if 0 <= i < len(self.pages)})
        if not valid or direction not in {-1, 1}:
            return
        selected = set(valid)
        can_move = (direction < 0 and valid[0] > 0) or (direction > 0 and valid[-1] < len(self.pages) - 1)
        if not can_move:
            return
        self._record()
        order = valid if direction < 0 else list(reversed(valid))
        for index in order:
            target = index + direction
            if 0 <= target < len(self.pages) and target not in selected:
                self.pages[index], self.pages[target] = self.pages[target], self.pages[index]
                selected.remove(index)
                selected.add(target)

    def apply_order(self, uids: list[str]) -> None:
        if uids == [page.uid for page in self.pages]:
            return
        mapping = {page.uid: page for page in self.pages}
        if set(mapping) != set(uids):
            raise ValueError("页面顺序包含未知或缺失页面。")
        self._record()
        self.pages[:] = [mapping[uid] for uid in uids]

    def undo(self) -> bool:
        if not self._undo:
            return False
        self._redo.append(self._snapshot())
        self.pages[:] = self._undo.pop().pages
        return True

    def redo(self) -> bool:
        if not self._redo:
            return False
        self._undo.append(self._snapshot())
        self.pages[:] = self._redo.pop().pages
        return True

    def reset(self) -> None:
        self.pages.clear()
        self._undo.clear()
        self._redo.clear()
