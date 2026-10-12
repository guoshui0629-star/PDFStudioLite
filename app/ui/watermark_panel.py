from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QStandardPaths, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QButtonGroup,
    QColorDialog,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QStackedWidget,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.core.watermark import WatermarkSpec, parse_page_range
from app.services.watermark_assets import installed_font_families
from app.ui.components.skeuomorphic_switch import SkeuomorphicSwitch
from app.ui.components.segmented_tab_bar import SegmentedTabBar
from app.ui.components.tactile_slider import TactileSlider


POSITION_OPTIONS = (
    ("左上", "top-left"), ("上中", "top-center"), ("右上", "top-right"),
    ("左中", "middle-left"), ("正中", "center"), ("右中", "middle-right"),
    ("左下", "bottom-left"), ("下中", "bottom-center"), ("右下", "bottom-right"),
)


class WatermarkPanel(QWidget):
    preview_changed = Signal()
    apply_requested = Signal()
    scan_requested = Signal()
    remove_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("WatermarkPanel")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.tabs = SegmentedTabBar()
        self.tabs.addTab("添加水印")
        self.tabs.addTab("移除水印 Beta")
        layout.addWidget(self.tabs)
        self.stack = QStackedWidget()
        self.stack.addWidget(self._build_add_page())
        self.stack.addWidget(self._build_remove_page())
        self.tabs.currentChanged.connect(self.stack.setCurrentIndex)
        layout.addWidget(self.stack, 1)
        self._connect_preview_controls()
        self._apply_preset(0)

    @staticmethod
    def _scroll_page(content: QWidget) -> QScrollArea:
        content.setObjectName("WatermarkScrollContent")
        scroll = QScrollArea()
        scroll.setObjectName("WatermarkScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(content)
        scroll.viewport().setObjectName("WatermarkViewport")
        return scroll

    def _build_add_page(self) -> QWidget:
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 8, 4, 4)
        layout.setSpacing(10)
        self.preset = QComboBox()
        self.preset.addItems(["浅灰斜向文字", "居中半透明文字", "平铺保密水印", "右下角版权标识"])
        self.preset.currentIndexChanged.connect(self._apply_preset)
        layout.addWidget(QLabel("水印预设", objectName="SectionTitle"))
        layout.addWidget(self.preset)
        self.kind = QComboBox()
        self.kind.addItems(["文字水印", "图片水印"])
        layout.addWidget(self.kind)

        self.text = QTextEdit("仅供内部使用")
        self.text.setAcceptRichText(False)
        self.text.setFixedHeight(62)
        self.text.setPlaceholderText("输入水印文字")
        layout.addWidget(self.text)
        self.font = QComboBox()
        self.font.setEditable(True)
        self.font.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        families = installed_font_families()
        self.font.addItems(families or ("Microsoft YaHei UI", "Segoe UI"))
        preferred = next((name for name in ("Microsoft YaHei UI", "微软雅黑", "Segoe UI") if name in families), self.font.itemText(0))
        self.font.setCurrentText(preferred)
        self.font.setToolTip("输入字体名称可搜索当前系统已安装字体")
        layout.addWidget(self.font)

        self.image_path = QLineEdit()
        self.image_path.setPlaceholderText("选择 PNG、JPG、WebP 等图片")
        choose_image = QPushButton("选择水印图片…")
        choose_image.clicked.connect(self._choose_image)
        image_row = QHBoxLayout()
        image_row.addWidget(self.image_path, 1)
        image_row.addWidget(choose_image)
        self.image_controls = QWidget()
        self.image_controls.setLayout(image_row)
        layout.addWidget(self.image_controls)

        form = QFormLayout()
        self.font_size = QSpinBox()
        self.font_size.setRange(8, 300)
        self.font_size.setValue(48)
        self.font_size.setSuffix(" pt")
        form.addRow("字号", self.font_size)
        color_row = QHBoxLayout()
        self.color = QLineEdit("#B0B0B0")
        choose_color = QPushButton("选择…")
        choose_color.clicked.connect(self._choose_color)
        color_row.addWidget(self.color, 1)
        color_row.addWidget(choose_color)
        form.addRow("颜色", color_row)
        self.opacity = TactileSlider(Qt.Orientation.Horizontal)
        self.opacity.setRange(0, 100)
        self.opacity.setValue(25)
        self.opacity.setAccessibleName("水印不透明度")
        self.opacity_label = QLabel("25%")
        opacity_row = QHBoxLayout()
        opacity_row.addWidget(self.opacity, 1)
        opacity_row.addWidget(self.opacity_label)
        form.addRow("不透明度", opacity_row)
        self.angle = QSpinBox()
        self.angle.setRange(-90, 90)
        self.angle.setValue(-45)
        self.angle.setSuffix("°")
        form.addRow("旋转角度", self.angle)
        style_row = QHBoxLayout()
        style_row.setSpacing(12)
        self.bold = SkeuomorphicSwitch()
        self.bold.setAccessibleName("启用粗体")
        self.italic = SkeuomorphicSwitch()
        self.italic.setAccessibleName("启用斜体")
        style_row.addWidget(QLabel("加粗"))
        style_row.addWidget(self.bold)
        style_row.addSpacing(8)
        style_row.addWidget(QLabel("斜体"))
        style_row.addWidget(self.italic)
        style_row.addStretch()
        form.addRow("字体样式", style_row)
        self.image_scale = QDoubleSpinBox()
        self.image_scale.setRange(1, 100)
        self.image_scale.setValue(28)
        self.image_scale.setSuffix("% 页宽")
        form.addRow("图片缩放", self.image_scale)
        layout.addLayout(form)

        layout.addWidget(QLabel("位置", objectName="SectionTitle"))
        position_grid = QGridLayout()
        position_grid.setSpacing(4)
        self.position_group = QButtonGroup(self)
        self.position_group.setExclusive(True)
        for index, (label, value) in enumerate(POSITION_OPTIONS):
            button = QToolButton()
            button.setText(label)
            button.setCheckable(True)
            button.setProperty("positionValue", value)
            button.setMinimumSize(52, 28)
            self.position_group.addButton(button)
            position_grid.addWidget(button, index // 3, index % 3)
            if value == "center":
                button.setChecked(True)
        layout.addLayout(position_grid)

        toggle_row = QHBoxLayout()
        toggle_row.addWidget(QLabel("平铺水印"))
        toggle_row.addStretch()
        self.tiled = SkeuomorphicSwitch()
        self.tiled.setAccessibleName("启用平铺水印")
        toggle_row.addWidget(self.tiled)
        layout.addLayout(toggle_row)
        self.tile_controls = QWidget()
        tile_form = QFormLayout(self.tile_controls)
        tile_form.setContentsMargins(0, 0, 0, 0)
        self.h_gap = QDoubleSpinBox()
        self.h_gap.setRange(0, 500)
        self.h_gap.setValue(72)
        self.h_gap.setSuffix(" pt")
        self.v_gap = QDoubleSpinBox()
        self.v_gap.setRange(0, 500)
        self.v_gap.setValue(72)
        self.v_gap.setSuffix(" pt")
        tile_form.addRow("水平间距", self.h_gap)
        tile_form.addRow("垂直间距", self.v_gap)
        layout.addWidget(self.tile_controls)

        scope_form = QFormLayout()
        self.scope = QComboBox()
        self.scope.addItems(["全部页面", "当前选中页面", "指定页码范围"])
        self.page_range = QLineEdit()
        self.page_range.setPlaceholderText("例如 1-5,8,10-12")
        self.page_range.setVisible(False)
        self.scope.currentIndexChanged.connect(lambda index: self.page_range.setVisible(index == 2))
        scope_form.addRow("作用范围", self.scope)
        scope_form.addRow("页码", self.page_range)
        self.layer = QComboBox()
        self.layer.addItems(["页面内容上方", "页面内容下方"])
        scope_form.addRow("水印层级", self.layer)
        layout.addLayout(scope_form)

        output_form = QFormLayout()
        desktop = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DesktopLocation)
        self.output_dir = QLineEdit(desktop or str(Path.home() / "Desktop"))
        browse_output = QPushButton("选择…")
        browse_output.clicked.connect(self._choose_output_dir)
        output_row = QHBoxLayout()
        output_row.addWidget(self.output_dir, 1)
        output_row.addWidget(browse_output)
        output_form.addRow("输出位置", output_row)
        self.filename = QLineEdit("PDF Studio Lite_水印.pdf")
        output_form.addRow("文件名", self.filename)
        layout.addLayout(output_form)
        self.status = QLabel("调整参数可实时预览；原文件保持不变。", objectName="Secondary")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.apply_button = QPushButton("应用水印并导出")
        self.apply_button.setObjectName("PrimaryButton")
        self.apply_button.clicked.connect(self.apply_requested)
        layout.addWidget(self.apply_button)
        layout.addStretch()
        self.kind.currentIndexChanged.connect(self._update_kind_visibility)
        self.tiled.toggled.connect(self.tile_controls.setVisible)
        self._update_kind_visibility()
        self.tile_controls.setVisible(False)
        return self._scroll_page(content)

    def _build_remove_page(self) -> QWidget:
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 8, 4, 4)
        title = QLabel("移除水印 Beta", objectName="SectionTitle")
        layout.addWidget(title)
        hint = QLabel("优先移除独立水印对象。复杂水印可能无法完整去除，请预览确认。", objectName="Secondary")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.remove_source = QLineEdit()
        self.remove_source.setReadOnly(True)
        choose = QPushButton("选择待检测 PDF…")
        choose.clicked.connect(self._choose_remove_source)
        source_row = QHBoxLayout()
        source_row.addWidget(self.remove_source, 1)
        source_row.addWidget(choose)
        layout.addLayout(source_row)
        self.scan_button = QPushButton("扫描水印对象")
        self.scan_button.clicked.connect(self.scan_requested)
        layout.addWidget(self.scan_button)
        self.detection_list = QListWidget()
        self.detection_list.setObjectName("WatermarkDetectionList")
        self.detection_list.setAccessibleName("水印检测结果")
        layout.addWidget(self.detection_list, 1)
        self.remove_status = QLabel("尚未扫描。", objectName="Secondary")
        self.remove_status.setWordWrap(True)
        layout.addWidget(self.remove_status)
        desktop = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DesktopLocation)
        self.remove_output = QLineEdit(str(Path(desktop or Path.home() / "Desktop") / "无水印_PDFStudioLite.pdf"))
        layout.addWidget(self.remove_output)
        self.remove_button = QPushButton("移除选中的安全水印")
        self.remove_button.setObjectName("DestructiveButton")
        self.remove_button.setEnabled(False)
        self.remove_button.clicked.connect(self.remove_requested)
        layout.addWidget(self.remove_button)
        return self._scroll_page(content)

    def _connect_preview_controls(self) -> None:
        for control in (self.kind, self.font, self.font_size, self.color, self.angle, self.bold, self.italic, self.image_scale, self.h_gap, self.v_gap, self.layer):
            signal = getattr(control, "currentTextChanged", None) or getattr(control, "valueChanged", None) or getattr(control, "textChanged", None) or getattr(control, "toggled", None)
            if signal:
                signal.connect(self.preview_changed)
        self.text.textChanged.connect(self.preview_changed)
        self.opacity.valueChanged.connect(self._opacity_changed)
        self.tiled.toggled.connect(self.preview_changed)
        self.position_group.buttonToggled.connect(lambda *_: self.preview_changed.emit())

    def _opacity_changed(self, value: int) -> None:
        self.opacity_label.setText(f"{value}%")
        self.preview_changed.emit()

    def _update_kind_visibility(self) -> None:
        is_image = self.kind.currentIndex() == 1
        self.text.setVisible(not is_image)
        self.font.setVisible(not is_image)
        self.font_size.setEnabled(not is_image)
        self.bold.setEnabled(not is_image)
        self.italic.setEnabled(not is_image)
        self.image_controls.setVisible(is_image)
        self.image_scale.setEnabled(is_image)
        self.preview_changed.emit()

    def _choose_image(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(self, "选择水印图片", "", "图片 (*.png *.jpg *.jpeg *.webp *.bmp *.tif *.tiff)")
        if filename:
            self.image_path.setText(filename)
            self.preview_changed.emit()

    def _choose_color(self) -> None:
        chosen = QColorDialog.getColor(QColor(self.color.text()), self, "选择水印颜色", QColorDialog.ColorDialogOption.ShowAlphaChannel)
        if chosen.isValid():
            self.color.setText(chosen.name(QColor.NameFormat.HexRgb).upper())

    def _choose_output_dir(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "选择水印输出位置", self.output_dir.text())
        if folder:
            self.output_dir.setText(folder)

    def _choose_remove_source(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(self, "选择待检测 PDF", "", "PDF 文件 (*.pdf)")
        if filename:
            self.set_remove_source(Path(filename))

    def set_remove_source(self, path: Path, *, automatic: bool = False) -> None:
        resolved = path.resolve()
        self.remove_source.setText(str(resolved))
        self.remove_output.setText(str(resolved.with_name(f"{resolved.stem}_无水印_PDFStudioLite.pdf")))
        self.detection_list.clear()
        self.remove_button.setEnabled(False)
        self.remove_status.setText("已从拖入文件自动开始扫描…" if automatic else "文件已选择，点击“扫描水印对象”。")

    def is_remove_mode(self) -> bool:
        return self.tabs.currentIndex() == 1

    def _apply_preset(self, index: int) -> None:
        if index == 0:
            self.color.setText("#B0B0B0"); self.opacity.setValue(25); self.angle.setValue(-45); self.tiled.setChecked(False); self._set_position("center")
        elif index == 1:
            self.color.setText("#8A8A8E"); self.opacity.setValue(35); self.angle.setValue(0); self.tiled.setChecked(False); self._set_position("center")
        elif index == 2:
            self.text.setPlainText("保密 · CONFIDENTIAL"); self.color.setText("#9A9A9A"); self.opacity.setValue(20); self.angle.setValue(-35); self.tiled.setChecked(True); self._set_position("center")
        else:
            self.text.setPlainText("© 版权所有"); self.color.setText("#707070"); self.opacity.setValue(45); self.angle.setValue(0); self.tiled.setChecked(False); self._set_position("bottom-right")
        self.preview_changed.emit()

    def _set_position(self, value: str) -> None:
        for button in self.position_group.buttons():
            if button.property("positionValue") == value:
                button.setChecked(True)
                return

    def spec(self) -> WatermarkSpec:
        checked = self.position_group.checkedButton()
        return WatermarkSpec(
            kind="image" if self.kind.currentIndex() == 1 else "text",
            label=self.text.toPlainText().strip() or (Path(self.image_path.text()).name if self.image_path.text() else "图片水印"),
            text=self.text.toPlainText(),
            font_family=self.font.currentText(),
            font_size=float(self.font_size.value()),
            color=self.color.text().strip(),
            opacity=self.opacity.value() / 100.0,
            rotation=float(self.angle.value()),
            bold=self.bold.isChecked(),
            italic=self.italic.isChecked(),
            position=str(checked.property("positionValue") if checked else "center"),
            tiled=self.tiled.isChecked(),
            horizontal_gap=self.h_gap.value(),
            vertical_gap=self.v_gap.value(),
            scale_percent=self.image_scale.value(),
            overlay=self.layer.currentIndex() == 0,
        )

    def selected_pages(self, page_count: int, selected_rows: list[int]) -> tuple[int, ...]:
        if self.scope.currentIndex() == 0:
            return tuple(range(page_count))
        if self.scope.currentIndex() == 1:
            if not selected_rows:
                raise ValueError("请先在中央区域选择需要添加水印的页面。")
            return tuple(selected_rows)
        return parse_page_range(self.page_range.text(), page_count)

    def output_path(self) -> Path:
        name = self.filename.text().strip() or "PDF Studio Lite_水印.pdf"
        if not name.lower().endswith(".pdf"):
            name += ".pdf"
        return Path(self.output_dir.text().strip()) / name

    def set_busy(self, busy: bool) -> None:
        self.apply_button.setEnabled(not busy)
        self.scan_button.setEnabled(not busy)
        self.remove_button.setEnabled(not busy and any(self._checked_removal_ids()))

    def _checked_removal_ids(self) -> list[str]:
        result: list[str] = []
        for index in range(self.detection_list.count()):
            item = self.detection_list.item(index)
            if item.checkState() == Qt.CheckState.Checked and item.data(Qt.ItemDataRole.UserRole):
                result.append(str(item.data(Qt.ItemDataRole.UserRole)))
        return result

    def checked_removal_ids(self) -> tuple[str, ...]:
        return tuple(self._checked_removal_ids())
