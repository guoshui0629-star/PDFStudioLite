from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from app.core.models import CompressionResult


class ExportResultDialog(QDialog):
    def __init__(self, path: Path, result: CompressionResult | None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.path = path
        self.setWindowTitle("导出完成")
        self.setMinimumWidth(460)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 20)
        layout.setSpacing(14)

        heading = QHBoxLayout()
        icon = QLabel("✓", objectName="SuccessBadge")
        icon.setFixedSize(36, 36)
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        heading.addWidget(icon)
        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        title_box.addWidget(QLabel("PDF 已成功导出", objectName="DialogTitle"))
        message = result.message if result is not None else "页面已按当前顺序保存。"
        detail = QLabel(message, objectName="Secondary")
        detail.setWordWrap(True)
        title_box.addWidget(detail)
        heading.addLayout(title_box, 1)
        layout.addLayout(heading)

        form = QFormLayout()
        path_label = QLabel(str(path), objectName="PathLabel")
        path_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        path_label.setWordWrap(True)
        form.addRow("保存位置", path_label)
        output_bytes = result.output_bytes if result is not None else path.stat().st_size
        form.addRow("实际大小", QLabel(self._format_size(output_bytes)))
        if result is not None and result.target_bytes is not None:
            form.addRow("目标大小", QLabel(self._format_size(result.target_bytes)))
            error = result.target_error_ratio
            error_bytes = abs(result.target_bytes - result.output_bytes)
            error_text = f"{self._format_size(error_bytes)}（{error:.1%}）" if error is not None else "—"
            form.addRow("目标误差", QLabel(error_text))
            state = "已达到（误差 ≤ 0.5 MB）" if result.reached_target else "未达到"
            form.addRow("压缩结果", QLabel(state))
        layout.addLayout(form)

        buttons = QDialogButtonBox()
        open_folder = QPushButton("打开所在文件夹")
        open_folder.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.parent))))
        done = buttons.addButton("完成", QDialogButtonBox.ButtonRole.AcceptRole)
        done.setObjectName("PrimaryButton")
        buttons.addButton(open_folder, QDialogButtonBox.ButtonRole.ActionRole)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)

    @staticmethod
    def _format_size(size: int) -> str:
        return f"{size / (1024 * 1024):.2f} MB" if size >= 1024 * 1024 else f"{size / 1024:.1f} KB"
