from __future__ import annotations

from PySide6.QtCore import QEvent, QObject
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import QAbstractScrollArea, QAbstractSpinBox, QComboBox, QSlider, QWidget


class OptionWheelGuard(QObject):
    """Prevent accidental option changes while preserving panel scrolling."""

    _blocked_types = (QComboBox, QAbstractSpinBox, QSlider)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        if event.type() != QEvent.Type.Wheel or not isinstance(watched, QWidget):
            return False
        control = self._option_control(watched)
        if control is None:
            return False
        wheel = event if isinstance(event, QWheelEvent) else None
        scroll_area = self._scroll_area(control)
        if wheel is not None and scroll_area is not None:
            bar = scroll_area.verticalScrollBar()
            delta = wheel.pixelDelta().y()
            if delta:
                bar.setValue(bar.value() - delta)
            else:
                steps = wheel.angleDelta().y() / 120.0
                bar.setValue(bar.value() - round(steps * max(bar.singleStep(), 20) * 3))
        event.accept()
        return True

    def _option_control(self, widget: QWidget) -> QWidget | None:
        current: QWidget | None = widget
        while current is not None:
            if isinstance(current, self._blocked_types):
                return current
            if isinstance(current, QAbstractScrollArea):
                return None
            current = current.parentWidget()
        return None

    @staticmethod
    def _scroll_area(widget: QWidget) -> QAbstractScrollArea | None:
        current = widget.parentWidget()
        while current is not None:
            if isinstance(current, QAbstractScrollArea):
                return current
            current = current.parentWidget()
        return None
