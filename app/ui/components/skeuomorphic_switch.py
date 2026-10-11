from __future__ import annotations

from PySide6.QtCore import Property, QEasingCurve, QEvent, QPointF, QPropertyAnimation, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFocusEvent, QKeyEvent, QLinearGradient, QPainter, QPaintEvent, QPen, QRadialGradient
from PySide6.QtWidgets import QAbstractButton, QHBoxLayout, QLabel, QWidget


class SkeuomorphicSwitch(QAbstractButton):
    """A high-DPI, keyboard-accessible four-layer tactile switch."""

    def __init__(self, parent=None) -> None:  # type: ignore[no-untyped-def]
        super().__init__(parent)
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAccessibleName("开关")
        self._position = 0.0
        self._hovered = False
        self._pressed = False
        self._animation = QPropertyAnimation(self, b"knobPosition", self)
        self._animation.setDuration(180)
        self._animation.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self.toggled.connect(self._animate_to_state)

    def sizeHint(self) -> QSize:
        return QSize(58, 32)

    def minimumSizeHint(self) -> QSize:
        return QSize(48, 26)

    def get_knob_position(self) -> float:
        return self._position

    def set_knob_position(self, value: float) -> None:
        self._position = max(0.0, min(float(value), 1.0))
        self.update()

    knobPosition = Property(float, get_knob_position, set_knob_position)

    def setChecked(self, checked: bool) -> None:  # noqa: N802
        super().setChecked(checked)
        if not self._animation.state():
            self.set_knob_position(1.0 if checked else 0.0)

    def _animate_to_state(self, checked: bool) -> None:
        self._animation.stop()
        self._animation.setStartValue(self._position)
        self._animation.setEndValue(1.0 if checked else 0.0)
        self._animation.start()

    def enterEvent(self, event: QEvent) -> None:
        self._hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event: QEvent) -> None:
        self._hovered = False
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        self._pressed = True
        self.update()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        self._pressed = False
        self.update()
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() in (Qt.Key.Key_Space, Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._pressed = True
            self.update()
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event: QKeyEvent) -> None:
        self._pressed = False
        self.update()
        super().keyReleaseEvent(event)

    def focusInEvent(self, event: QFocusEvent) -> None:
        self.update()
        super().focusInEvent(event)

    def focusOutEvent(self, event: QFocusEvent) -> None:
        self.update()
        super().focusOutEvent(event)

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        scale = min(self.width() / 58.0, self.height() / 32.0)
        width, height = 52.0 * scale, 28.0 * scale
        outer = QRectF((self.width() - width) / 2, (self.height() - height) / 2, width, height)
        radius = height / 2

        # Layer 1: precision metal outline and a restrained cast shadow.
        shadow = outer.translated(0, 1.5 * scale)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0, 45 if self.isEnabled() else 20))
        painter.drawRoundedRect(shadow, radius, radius)
        rim = QLinearGradient(outer.topLeft(), outer.bottomLeft())
        rim.setColorAt(0.0, QColor("#F4F4F2"))
        rim.setColorAt(0.45, QColor("#A6A6A2"))
        rim.setColorAt(1.0, QColor("#666662"))
        painter.setBrush(rim)
        painter.drawRoundedRect(outer, radius, radius)

        # Layer 2 and 3: recessed track with state color and internal shade.
        track = outer.adjusted(2.2 * scale, 2.2 * scale, -2.2 * scale, -2.2 * scale)
        off = QColor("#444548")
        on = QColor("#F47B20")
        mix = self._position
        state = QColor(
            round(off.red() * (1 - mix) + on.red() * mix),
            round(off.green() * (1 - mix) + on.green() * mix),
            round(off.blue() * (1 - mix) + on.blue() * mix),
        )
        if not self.isEnabled():
            state = QColor("#777777")
        track_gradient = QLinearGradient(track.topLeft(), track.bottomLeft())
        track_gradient.setColorAt(0.0, state.darker(155))
        track_gradient.setColorAt(0.25, state.darker(112))
        track_gradient.setColorAt(0.7, state)
        track_gradient.setColorAt(1.0, state.lighter(112))
        painter.setBrush(track_gradient)
        painter.setPen(QPen(QColor(20, 20, 20, 115), max(0.7, scale)))
        painter.drawRoundedRect(track, track.height() / 2, track.height() / 2)
        painter.setPen(QPen(QColor(255, 255, 255, 55), max(0.6, scale)))
        painter.drawArc(track.adjusted(scale, scale, -scale, -scale), 20 * 16, 140 * 16)

        # Layer 4: a tangible metal knob with edge depth and concentric machining.
        knob_diameter = track.height() - 2.0 * scale
        travel = track.width() - knob_diameter - 2.0 * scale
        knob_x = track.left() + scale + travel * self._position
        knob_y = track.top() + scale + (1.0 * scale if self._pressed else 0.0)
        knob = QRectF(knob_x, knob_y, knob_diameter, knob_diameter)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0, 70 if not self._pressed else 45))
        painter.drawEllipse(knob.translated(1.1 * scale, 1.8 * scale))
        knob_fill = QRadialGradient(knob.center(), knob_diameter * 0.65)
        knob_fill.setCenter(knob.center() - QPointF(knob_diameter * 0.18, knob_diameter * 0.2))
        knob_fill.setFocalPoint(knob.center() - QPointF(knob_diameter * 0.22, knob_diameter * 0.25))
        knob_fill.setColorAt(0.0, QColor("#FFFFFF" if self.isEnabled() else "#D0D0D0"))
        knob_fill.setColorAt(0.58, QColor("#D8D8D4"))
        knob_fill.setColorAt(1.0, QColor("#8D8D89"))
        painter.setBrush(knob_fill)
        painter.setPen(QPen(QColor("#6E6E6A"), max(0.7, scale)))
        painter.drawEllipse(knob)
        center = knob.center()
        painter.setBrush(Qt.BrushStyle.NoBrush)
        for index in range(1, 8):
            inset = index * knob_diameter / 18.0
            alpha = 35 if index % 2 else 20
            painter.setPen(QPen(QColor(70, 70, 68, alpha), max(0.35, scale * 0.35)))
            painter.drawEllipse(knob.adjusted(inset, inset, -inset, -inset))
        painter.setPen(QPen(QColor(255, 255, 255, 115), max(0.7, scale)))
        painter.drawArc(knob.adjusted(scale, scale, -scale, -scale), 35 * 16, 120 * 16)

        if self._hovered and self.isEnabled():
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor(244, 123, 32, 90), max(1.0, scale)))
            painter.drawRoundedRect(outer.adjusted(-0.5 * scale, -0.5 * scale, 0.5 * scale, 0.5 * scale), radius + scale, radius + scale)
        if self.hasFocus():
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor("#F47B20"), max(1.5, 1.5 * scale)))
            focus_rect = self.rect().adjusted(1, 1, -1, -1)
            painter.drawRoundedRect(focus_rect, focus_rect.height() / 2, focus_rect.height() / 2)
        painter.end()


class LabeledSwitch(QWidget):
    """Text label paired with the reference-video tactile switch."""

    toggled = Signal(bool)

    def __init__(self, text: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("LabeledSwitch")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 2)
        layout.setSpacing(10)
        self.label = QLabel(text)
        self.switch = SkeuomorphicSwitch()
        self.switch.setAccessibleName(text)
        layout.addWidget(self.label)
        layout.addStretch()
        layout.addWidget(self.switch)
        self.switch.toggled.connect(self.toggled)

    def isChecked(self) -> bool:  # noqa: N802
        return self.switch.isChecked()

    def setChecked(self, checked: bool) -> None:  # noqa: N802
        self.switch.setChecked(checked)

    def setEnabled(self, enabled: bool) -> None:  # noqa: N802
        super().setEnabled(enabled)
        self.label.setEnabled(enabled)
        self.switch.setEnabled(enabled)

    def setToolTip(self, tip: str) -> None:  # noqa: N802
        super().setToolTip(tip)
        self.label.setToolTip(tip)
        self.switch.setToolTip(tip)
