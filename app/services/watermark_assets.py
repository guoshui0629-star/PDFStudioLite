from __future__ import annotations

from io import BytesIO
from pathlib import Path

from PIL import Image, ImageEnhance, ImageOps
from PySide6.QtCore import QByteArray, QBuffer, QIODevice, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase, QFontMetricsF, QImage, QPainter, QTransform
from PySide6.QtWidgets import QApplication

from app.core.watermark import WatermarkAsset, WatermarkSpec


TEXT_RENDER_SCALE = 2.0


def installed_font_families() -> tuple[str, ...]:
    if QApplication.instance() is None:
        raise RuntimeError("读取系统字体前必须先创建 QApplication。")
    return tuple(sorted(QFontDatabase.families(), key=str.casefold))


def _qimage_png(image: QImage) -> bytes:
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    if not image.save(buffer, "PNG"):
        raise RuntimeError("无法生成文字水印图像。")
    return bytes(data)


def render_text_asset(spec: WatermarkSpec) -> WatermarkAsset:
    text = spec.text.strip()
    if not text:
        raise ValueError("请输入水印文字。")
    font = QFont(spec.font_family)
    font.setPixelSize(max(2, round(spec.font_size * TEXT_RENDER_SCALE)))
    font.setBold(spec.bold)
    font.setItalic(spec.italic)
    metrics = QFontMetricsF(font)
    text_rect = metrics.boundingRect(QRectF(0, 0, 4096, 4096), int(Qt.AlignmentFlag.AlignCenter), text)
    padding = max(12, round(spec.font_size * 0.35 * TEXT_RENDER_SCALE))
    width = max(2, round(text_rect.width()) + padding * 2)
    height = max(2, round(text_rect.height()) + padding * 2)
    image = QImage(width, height, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    color = QColor(spec.color)
    if not color.isValid():
        raise ValueError("水印颜色格式无效。")
    color.setAlphaF(max(0.0, min(spec.opacity, 1.0)))
    painter.setPen(color)
    painter.setFont(font)
    painter.drawText(QRectF(padding, padding, width - 2 * padding, height - 2 * padding), int(Qt.AlignmentFlag.AlignCenter), text)
    painter.end()
    if spec.rotation:
        image = image.transformed(QTransform().rotate(spec.rotation), Qt.TransformationMode.SmoothTransformation)
    return WatermarkAsset(_qimage_png(image), image.width() / TEXT_RENDER_SCALE, image.height() / TEXT_RENDER_SCALE)


def render_image_asset(spec: WatermarkSpec, image_path: str | Path) -> WatermarkAsset:
    path = Path(image_path)
    if path.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}:
        raise ValueError("水印图片必须是 PNG、JPG、WebP、BMP 或 TIFF。")
    with Image.open(path) as source:
        dpi = source.info.get("dpi", (72, 72))
        image = ImageOps.exif_transpose(source).convert("RGBA")
    alpha = image.getchannel("A")
    alpha = ImageEnhance.Brightness(alpha).enhance(max(0.0, min(spec.opacity, 1.0)))
    image.putalpha(alpha)
    if spec.rotation:
        image = image.rotate(-spec.rotation, expand=True, resample=Image.Resampling.BICUBIC)
    stream = BytesIO()
    image.save(stream, "PNG", compress_level=6)
    dpi_x = float(dpi[0] or 72)
    dpi_y = float(dpi[1] or 72)
    return WatermarkAsset(stream.getvalue(), image.width * 72.0 / dpi_x, image.height * 72.0 / dpi_y)


def render_watermark_asset(spec: WatermarkSpec, image_path: str | Path | None = None) -> WatermarkAsset:
    if spec.kind == "image":
        if image_path is None:
            raise ValueError("请选择水印图片。")
        return render_image_asset(spec, image_path)
    return render_text_asset(spec)
