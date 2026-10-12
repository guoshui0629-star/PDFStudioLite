from __future__ import annotations

import sys

from PySide6.QtCore import QCoreApplication, Qt
from PySide6.QtGui import QFont, QFontDatabase, QIcon
from PySide6.QtWidgets import QApplication

from app.ui.main_window import MainWindow
from app.ui.theme import application_stylesheet
from app.ui.wheel_guard import OptionWheelGuard
from app.resources import ui_resource_path


def create_application(argv: list[str] | None = None) -> QApplication:
    existing = QApplication.instance()
    if isinstance(existing, QApplication):
        return existing
    QCoreApplication.setApplicationName("PDF Studio Lite")
    QCoreApplication.setOrganizationName("PDF Studio Lite")
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(argv if argv is not None else sys.argv)
    families = set(QFontDatabase.families())
    preferred_families = (
        ("PingFang SC", ".AppleSystemUIFont", "Helvetica Neue", "Arial")
        if sys.platform == "darwin"
        else ("Microsoft YaHei UI", "Segoe UI Variable", "Segoe UI", "Arial")
    )
    family = next((name for name in preferred_families if name in families), QApplication.font().family())
    font = QFont(family, 10)
    app.setFont(font)
    app.setWindowIcon(QIcon(str(ui_resource_path("assets/branding/pdf-toaster-app-512.png"))))
    app.setProperty("darkTheme", False)
    app.setStyleSheet(application_stylesheet())
    app.option_wheel_guard = OptionWheelGuard(app)  # type: ignore[attr-defined]
    app.installEventFilter(app.option_wheel_guard)  # type: ignore[attr-defined]
    return app


def main() -> int:
    app = create_application()
    if "--self-test" in sys.argv:
        # Reaching this point proves that QtCore/QtGui/QtWidgets and the platform
        # plugin loaded successfully in both source and packaged builds.
        return 0
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
