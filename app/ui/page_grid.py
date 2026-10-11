from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QMimeData, QPoint, Qt, Signal
from PySide6.QtGui import QDragEnterEvent, QDragLeaveEvent, QDragMoveEvent, QDropEvent, QKeyEvent, QMouseEvent, QPainter, QPaintEvent, QPen
from PySide6.QtWidgets import QAbstractItemView, QListWidget, QPushButton

from app.core.document import SUPPORTED_IMAGES


def reordered_uids(uids: list[str], selected_rows: list[int], destination: int) -> list[str]:
    valid = sorted({row for row in selected_rows if 0 <= row < len(uids)})
    if not valid:
        return uids
    moving = [uids[row] for row in valid]
    selected = set(valid)
    remaining = [uid for row, uid in enumerate(uids) if row not in selected]
    adjusted = destination - sum(row < destination for row in valid)
    adjusted = max(0, min(adjusted, len(remaining)))
    return remaining[:adjusted] + moving + remaining[adjusted:]


class PageGrid(QListWidget):
    files_dropped = Signal(list, int)
    order_changed = Signal(list)
    delete_requested = Signal()
    open_preview_requested = Signal(int)
    context_menu_requested = Signal(QPoint)
    rotate_page_requested = Signal(int)

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("PageGrid")
        self.setViewMode(QListWidget.ViewMode.IconMode)
        self.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.setMovement(QListWidget.Movement.Snap)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setSpacing(8)
        self.setUniformItemSizes(True)
        self.setAutoScroll(True)
        self.setDragDropOverwriteMode(False)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self.context_menu_requested)
        self.setAccessibleName("PDF 页面缩略图")
        self.itemDoubleClicked.connect(lambda item: self.open_preview_requested.emit(self.row(item)))
        self._drop_index: int | None = None
        self._hover_row = -1
        self.setMouseTracking(True)
        self.viewport().setMouseTracking(True)
        self.rotate_button = QPushButton("↷", self.viewport())
        self.rotate_button.setObjectName("PageRotateButton")
        self.rotate_button.setFixedSize(28, 28)
        self.rotate_button.setToolTip("旋转此页 90°")
        self.rotate_button.clicked.connect(lambda: self.rotate_page_requested.emit(self._hover_row) if self._hover_row >= 0 else None)
        self.rotate_button.hide()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        index = self.indexAt(event.position().toPoint())
        self._hover_row = index.row() if index.isValid() else -1
        if index.isValid():
            rect = self.visualRect(index)
            self.rotate_button.move(rect.right() - self.rotate_button.width() - 6, rect.top() + 6)
            self.rotate_button.show()
            self.rotate_button.raise_()
        else:
            self.rotate_button.hide()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        self.rotate_button.hide()
        self._hover_row = -1
        super().leaveEvent(event)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event: QDragMoveEvent) -> None:
        self._drop_index = self._insertion_index(event.position().toPoint())
        self.viewport().update()
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.acceptProposedAction()

    def dragLeaveEvent(self, event: QDragLeaveEvent) -> None:
        self._drop_index = None
        self.viewport().update()
        super().dragLeaveEvent(event)

    def dropEvent(self, event: QDropEvent) -> None:
        target = self._insertion_index(event.position().toPoint())
        self._drop_index = None
        self.viewport().update()
        if event.mimeData().hasUrls():
            files = [
                url.toLocalFile()
                for url in event.mimeData().urls()
                if url.isLocalFile()
                and (Path(url.toLocalFile()).suffix.lower() == ".pdf" or Path(url.toLocalFile()).suffix.lower() in SUPPORTED_IMAGES)
            ]
            if not files:
                event.ignore()
                return
            self.files_dropped.emit(files, target)
            event.acceptProposedAction()
            return
        rows = sorted(self.row(item) for item in self.selectedItems())
        uids = [self.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.count())]
        self.order_changed.emit(reordered_uids(uids, rows, target))
        event.setDropAction(Qt.DropAction.MoveAction)
        event.accept()

    def _insertion_index(self, point: QPoint) -> int:
        if self.count() == 0:
            return 0
        rects = [(row, self.visualItemRect(self.item(row))) for row in range(self.count())]
        if point.y() < min(rect.top() for _, rect in rects):
            return 0
        if point.y() > max(rect.bottom() for _, rect in rects):
            return self.count()
        row, rect = min(
            rects,
            key=lambda pair: (pair[1].center().x() - point.x()) ** 2 + (pair[1].center().y() - point.y()) ** 2,
        )
        return row + (1 if point.x() >= rect.center().x() else 0)

    def paintEvent(self, event: QPaintEvent) -> None:
        super().paintEvent(event)
        if self._drop_index is None or self.count() == 0:
            return
        if self._drop_index >= self.count():
            rect = self.visualItemRect(self.item(self.count() - 1))
            x = rect.right() + max(3, self.spacing() // 2)
        else:
            rect = self.visualItemRect(self.item(self._drop_index))
            x = rect.left() - max(3, self.spacing() // 2)
        painter = QPainter(self.viewport())
        painter.setPen(QPen(self.palette().highlight().color(), 3))
        painter.drawLine(x, rect.top() + 4, x, rect.bottom() - 4)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            self.delete_requested.emit()
            event.accept()
            return
        super().keyPressEvent(event)
