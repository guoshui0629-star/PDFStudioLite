from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPaintEvent, QPen, QRadialGradient
from PySide6.QtWidgets import QApplication, QSlider


class TactileSlider(QSlider):
    """A compact antialiased slider with a circular, shadowed thumb."""

    handle_diameter = 22

    def __init__(self, orientation: Qt.Orientation, parent=None) -> None:  # type: ignore[no-untyped-def]
        super().__init__(orientation, parent)
        self.setObjectName("ThumbnailSlider")
        self.setMinimumHeight(34)

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        dark = bool(QApplication.instance() and QApplication.instance().property("darkTheme"))
        diameter = float(self.handle_diameter)
        radius = diameter / 2.0
        padding = radius + 3.0
        span = max(1.0, self.width() - padding * 2.0)
        ratio = (self.value() - self.minimum()) / max(1, self.maximum() - self.minimum())
        center_x = padding + span * ratio
        center_y = self.height() / 2.0

        groove = QRectF(padding, center_y - 2.5, span, 5.0)
        painter.setPen(QPen(QColor("#68696D" if dark else "#A8A8A2"), 1.0))
        painter.setBrush(QColor("#4A4B4E" if dark else "#C8C8C3"))
        painter.drawRoundedRect(groove, 2.5, 2.5)
        filled = QRectF(groove.left(), groove.top(), max(0.0, center_x - groove.left()), groove.height())
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#F07A32" if dark else "#E66A1F"))
        painter.drawRoundedRect(filled, 2.5, 2.5)

        shadow = QRectF(center_x - radius - 2.0, center_y - radius + 1.0, diameter + 4.0, diameter + 5.0)
        shadow_gradient = QRadialGradient(shadow.center(), shadow.width() / 2.0)
        shadow_gradient.setColorAt(0.55, QColor(0, 0, 0, 75 if dark else 55))
        shadow_gradient.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.setBrush(shadow_gradient)
        painter.drawEllipse(shadow)

        handle = QRectF(center_x - radius, center_y - radius, diameter, diameter)
        metal = QLinearGradient(handle.topLeft(), handle.bottomRight())
        metal.setColorAt(0.0, QColor("#FFFFFF" if not dark else "#F4F4F1"))
        metal.setColorAt(0.48, QColor("#DADAD5" if not dark else "#BFC0C2"))
        metal.setColorAt(1.0, QColor("#969691" if not dark else "#737478"))
        painter.setPen(QPen(QColor("#777772" if not dark else "#9A9B9F"), 1.0))
        painter.setBrush(metal)
        painter.drawEllipse(handle)
        if self.hasFocus():
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor("#F29A5F"), 2.0))
            painter.drawEllipse(handle.adjusted(-2.0, -2.0, 2.0, 2.0))
        painter.end()
