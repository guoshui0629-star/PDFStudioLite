from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QKeyEvent, QMouseEvent, QPainter, QPaintEvent, QPen, QResizeEvent
from PySide6.QtWidgets import QListWidget, QPushButton


class CenteredCloseButton(QPushButton):
    """Draw a close glyph around the geometric center, independent of font metrics."""

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        color = QColor("#FFFFFF" if self.underMouse() else "#FFB080")
        painter.setPen(QPen(color, 1.7, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        center = self.rect().center()
        extent = 4
        painter.drawLine(center.x() - extent, center.y() - extent, center.x() + extent, center.y() + extent)
        painter.drawLine(center.x() + extent, center.y() - extent, center.x() - extent, center.y() + extent)
        painter.end()


class SourceList(QListWidget):
    """Imported-file list with keyboard and inline removal affordances."""

    remove_requested = Signal(Path)

    def __init__(self, parent=None) -> None:  # type: ignore[no-untyped-def]
        super().__init__(parent)
        self.setObjectName("SourceList")
        self.setMouseTracking(True)
        self.viewport().setMouseTracking(True)
        self.remove_button = CenteredCloseButton("", self.viewport())
        self.remove_button.setObjectName("SourceRemoveButton")
        self.remove_button.setAccessibleName("删除此文件")
        self.remove_button.setFixedSize(24, 24)
        self.remove_button.setToolTip("删除此文件的全部页面（可撤销）")
        self.remove_button.clicked.connect(self._remove_current)
        self.remove_button.hide()
        self.itemSelectionChanged.connect(self._position_remove_button)
        self.verticalScrollBar().valueChanged.connect(self._position_remove_button)

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace) and self.currentItem() is not None:
            self._remove_current()
            event.accept()
            return
        super().keyPressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        item = self.itemAt(event.position().toPoint())
        if item is not None and not item.isSelected():
            self.setCurrentItem(item)
        self._position_remove_button()
        super().mouseMoveEvent(event)

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._position_remove_button()

    def leaveEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        if self.currentItem() is None or not self.currentItem().isSelected():
            self.remove_button.hide()
        super().leaveEvent(event)

    def _position_remove_button(self) -> None:
        item = self.currentItem()
        if item is None or not item.isSelected():
            self.remove_button.hide()
            return
        rect = self.visualItemRect(item)
        if not rect.isValid() or not self.viewport().rect().intersects(rect):
            self.remove_button.hide()
            return
        self.remove_button.move(rect.right() - self.remove_button.width() - 7, rect.center().y() - self.remove_button.height() // 2)
        self.remove_button.show()
        self.remove_button.raise_()

    def _remove_current(self) -> None:
        item = self.currentItem()
        if item is None:
            return
        source = item.data(Qt.ItemDataRole.UserRole)
        if source:
            self.remove_requested.emit(Path(str(source)))
