from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QImage, QPainter, QPixmap

from app.core.watermark import WatermarkAsset, WatermarkSpec


def draw_watermark_preview(base: QImage, asset: WatermarkAsset, spec: WatermarkSpec) -> QImage:
    result = base.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)
    mark_image = QImage.fromData(asset.png, "PNG")
    if mark_image.isNull():
        return result
    ratio = mark_image.height() / max(mark_image.width(), 1)
    if spec.kind == "image":
        width = result.width() * max(0.01, min(spec.scale_percent, 100.0)) / 100.0
    else:
        width = min(mark_image.width(), result.width() * (0.52 if spec.tiled else 0.82))
    height = width * ratio
    if height > result.height() * 0.82:
        factor = result.height() * 0.82 / height
        width, height = width * factor, height * factor
    margin = min(result.width(), result.height()) * 0.05
    columns = {"left": margin, "center": (result.width() - width) / 2, "right": result.width() - margin - width}
    rows = {"top": margin, "middle": (result.height() - height) / 2, "bottom": result.height() - margin - height}
    vertical, horizontal = {
        "top-left": ("top", "left"), "top-center": ("top", "center"), "top-right": ("top", "right"),
        "middle-left": ("middle", "left"), "center": ("middle", "center"), "middle-right": ("middle", "right"),
        "bottom-left": ("bottom", "left"), "bottom-center": ("bottom", "center"), "bottom-right": ("bottom", "right"),
    }.get(spec.position, ("middle", "center"))
    painter = QPainter(result)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    pixmap = QPixmap.fromImage(mark_image)
    if spec.tiled:
        point_scale = result.width() / 595.0
        x_step = width + spec.horizontal_gap * point_scale
        y_step = height + spec.vertical_gap * point_scale
        y, row = spec.vertical_gap * point_scale / 2, 0
        while y < result.height():
            x = spec.horizontal_gap * point_scale / 2 - (x_step / 2 if row % 2 else 0)
            while x < result.width():
                painter.drawPixmap(QRectF(x, y, width, height), pixmap, QRectF(pixmap.rect()))
                x += max(1.0, x_step)
            y += max(1.0, y_step)
            row += 1
    else:
        painter.drawPixmap(QRectF(columns[horizontal], rows[vertical], width, height), pixmap, QRectF(pixmap.rect()))
    painter.end()
    return result
