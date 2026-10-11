from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from app.main import create_application
from app.ui.components.skeuomorphic_switch import SkeuomorphicSwitch


def test_switch_supports_mouse_keyboard_and_disabled_state() -> None:
    existing = QApplication.instance()
    app = existing or create_application([])
    switch = SkeuomorphicSwitch()
    switch.show()
    app.processEvents()
    assert not switch.isChecked()
    QTest.mouseClick(switch, Qt.MouseButton.LeftButton)
    app.processEvents()
    assert switch.isChecked()
    switch.setFocus()
    QTest.keyClick(switch, Qt.Key.Key_Space)
    app.processEvents()
    assert not switch.isChecked()
    switch.setEnabled(False)
    QTest.mouseClick(switch, Qt.MouseButton.LeftButton)
    assert not switch.isChecked()
    if existing is None:
        app.quit()
