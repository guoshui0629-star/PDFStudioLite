from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import StrEnum
from pathlib import Path
from uuid import uuid4


class SourceKind(StrEnum):
    PDF = "pdf"
    IMAGE = "image"


class ImageLayout(StrEnum):
    ORIGINAL = "original"
    A4 = "a4"
    FIT = "fit"


@dataclass(frozen=True, slots=True)
class PageRef:
    source: Path
    kind: SourceKind
    source_page: int = 0
    rotation: int = 0
    image_layout: ImageLayout = ImageLayout.ORIGINAL
    uid: str = field(default_factory=lambda: uuid4().hex)

    def rotated(self, degrees: int) -> "PageRef":
        return replace(self, rotation=(self.rotation + degrees) % 360, uid=uuid4().hex)

    def duplicate(self) -> "PageRef":
        return replace(self, uid=uuid4().hex)


@dataclass(frozen=True, slots=True)
class DocumentSnapshot:
    pages: tuple[PageRef, ...]


@dataclass(frozen=True, slots=True)
class PdfFeatureReport:
    encrypted: bool = False
    has_bookmarks: bool = False
    has_links: bool = False
    has_forms: bool = False
    has_annotations: bool = False
    has_attachments: bool = False
    has_signatures: bool = False

    @property
    def warnings(self) -> list[str]:
        result: list[str] = []
        if self.has_signatures:
            result.append("编辑后数字签名将失效。")
        if self.has_forms:
            result.append("交互式表单在页面重组后可能无法完整保留。")
        if self.has_bookmarks or self.has_links:
            result.append("书签或内部链接在页面重排后可能需要重新校验。")
        if self.has_annotations or self.has_attachments:
            result.append("检测到注释或附件；导出后请核对其完整性。")
        return result


@dataclass(frozen=True, slots=True)
class CompressionResult:
    output_path: Path
    original_bytes: int
    output_bytes: int
    target_bytes: int | None
    reached_target: bool
    mode: str
    message: str

    @property
    def ratio(self) -> float:
        if not self.original_bytes:
            return 0.0
        return 1.0 - self.output_bytes / self.original_bytes

    @property
    def target_error_ratio(self) -> float | None:
        if not self.target_bytes:
            return None
        return abs(self.output_bytes - self.target_bytes) / self.target_bytes
