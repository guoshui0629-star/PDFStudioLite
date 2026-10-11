from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPaintEvent, QPen
from PySide6.QtWidgets import QApplication, QTabBar


class SegmentedTabBar(QTabBar):
    """Antialiased segmented selector that avoids QSS rounded-corner artifacts."""

    def __init__(self, parent=None) -> None:  # type: ignore[no-untyped-def]
        super().__init__(parent)
        self.setObjectName("SegmentedTabBar")
        self.setDocumentMode(True)
        self.setExpanding(True)
        self.setDrawBase(False)
        self.setMinimumHeight(44)

    def tabSizeHint(self, index: int) -> QSize:  # noqa: N802
        hint = super().tabSizeHint(index)
        return QSize(max(64, hint.width()), 42)

    def paintEvent(self, event: QPaintEvent) -> None:
        del event
        application = QApplication.instance()
        dark = bool(application and application.property("darkTheme"))
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        painter.fillRect(self.rect(), QColor("#27282A" if dark else "#EFEFEC"))
        outer = self.rect().adjusted(1, 1, -1, -1)
        radius = 10.0
        path = QPainterPath()
        path.addRoundedRect(outer, radius, radius)

        base = QLinearGradient(outer.topLeft(), outer.bottomLeft())
        base.setColorAt(0.0, QColor("#3B3C3F" if dark else "#F8F8F5"))
        base.setColorAt(1.0, QColor("#292A2C" if dark else "#D7D7D2"))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(base)
        painter.drawPath(path)

        painter.save()
        painter.setClipPath(path)
        selected = self.currentIndex()
        if 0 <= selected < self.count():
            rect = self.tabRect(selected).adjusted(0, 1, 0, -1)
            active = QLinearGradient(rect.topLeft(), rect.bottomLeft())
            active.setColorAt(0.0, QColor("#505155" if dark else "#FFFFFF"))
            active.setColorAt(1.0, QColor("#353638" if dark else "#ECECE8"))
            painter.fillRect(rect, active)
            painter.fillRect(rect.adjusted(0, rect.height() - 3, 0, 0), QColor("#E66A1F"))

        painter.setPen(QPen(QColor("#55565A" if dark else "#B4B4AE"), 1.0))
        for index in range(1, self.count()):
            x = self.tabRect(index).left()
            painter.drawLine(x, outer.top() + 4, x, outer.bottom() - 4)
        painter.restore()

        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor("#636469" if dark else "#AFAFAA"), 1.0))
        painter.drawPath(path)

        for index in range(self.count()):
            rect = self.tabRect(index)
            selected_tab = index == self.currentIndex()
            painter.setPen(
                QColor("#FFB080" if dark else "#87320D")
                if selected_tab
                else QColor("#F2F2EF" if dark else "#292927")
            )
            font = painter.font()
            font.setWeight(QFont.Weight.DemiBold if selected_tab else QFont.Weight.Normal)
            painter.setFont(font)
            painter.drawText(rect.adjusted(4, 0, -4, -2), Qt.AlignmentFlag.AlignCenter, self.tabText(index))
        painter.end()
