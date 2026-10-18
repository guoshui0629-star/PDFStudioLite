from __future__ import annotations

import os
from pathlib import Path

import pymupdf
from PySide6.QtCore import QByteArray, QEvent, QSize, QStandardPaths, Qt, QThreadPool, QTimer, Signal
from PySide6.QtGui import QAction, QActionGroup, QCloseEvent, QDragEnterEvent, QDropEvent, QIcon, QImage, QKeySequence, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSlider,
    QSpinBox,
    QSplitter,
    QStatusBar,
    QStackedWidget,
    QStyle,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from app import __product_title__
from app.core.compression import compress_to_target, lossless_optimize
from app.core.document import DocumentModel
from app.core.models import CompressionResult, PageRef
from app.core.pdf_engine import export_pages, inspect_pdf, render_thumbnail
from app.core.workspace import WorkspaceMode
from app.core.watermark import WatermarkAsset, WatermarkRecord, apply_watermark, remove_watermarks, scan_watermarks
from app.resources import resource_path, ui_resource_path
from app.services.image_export import export_page_images
from app.services.watermark_assets import render_watermark_asset
from app.ui.page_grid import PageGrid
from app.ui.components.skeuomorphic_switch import LabeledSwitch
from app.ui.components.segmented_tab_bar import SegmentedTabBar
from app.ui.components.tactile_slider import TactileSlider
from app.ui.result_dialog import ExportResultDialog
from app.ui.source_list import SourceList
from app.ui.theme import apply_theme
from app.ui.watermark_panel import WatermarkPanel
from app.ui.watermark_preview import draw_watermark_preview
from app.workers.tasks import FunctionTask


FILE_FILTER = "支持的文件 (*.pdf *.jpg *.jpeg *.png *.webp *.bmp *.tif *.tiff)"
SUPPORTED_SUFFIXES = {".pdf", ".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}
PAGE_SIZES_MM = {
    "A3 — 297 × 420 mm": (297.0, 420.0),
    "A4 — 210 × 297 mm": (210.0, 297.0),
    "A5 — 148 × 210 mm": (148.0, 210.0),
    "A6 — 105 × 148 mm": (105.0, 148.0),
    "B4 — 250 × 353 mm": (250.0, 353.0),
    "B5 — 176 × 250 mm": (176.0, 250.0),
    "Letter — 215.9 × 279.4 mm": (215.9, 279.4),
    "Legal — 215.9 × 355.6 mm": (215.9, 355.6),
}


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.model = DocumentModel()
        self.pool = QThreadPool.globalInstance()
        self.active_task: FunctionTask | None = None
        self.pending_watermark_scan: Path | None = None
        self.thumbnail_size = 150
        self.image_checked_uids: set[str] = set()
        self.known_page_uids: set[str] = set()
        self.workspace_mode = WorkspaceMode.PDF
        self.batch_files: list[Path] = []
        self.thumbnail_cache: dict[str, bytes] = {}
        self.watermark_preview_asset: WatermarkAsset | None = None
        self.watermark_preview_timer = QTimer(self)
        self.watermark_preview_timer.setSingleShot(True)
        self.watermark_preview_timer.setInterval(160)
        self.watermark_preview_timer.timeout.connect(self.refresh_watermark_preview)
        self.setWindowTitle(__product_title__)
        self.setWindowIcon(QIcon(str(ui_resource_path("assets/branding/pdf-toaster-app.ico"))))
        self.resize(1360, 860)
        self.setMinimumSize(900, 620)
        self.setAcceptDrops(True)
        self._build_actions()
        self._build_menu()
        self._build_toolbar()
        self._build_content()
        self._build_statusbar()
        self._update_actions()

    def _icon(self, icon: QStyle.StandardPixmap) -> QIcon:
        return self.style().standardIcon(icon)

    @staticmethod
    def _ui_icon(name: str) -> QIcon:
        return QIcon(str(ui_resource_path(f"assets/icons/{name}.svg")))

    def _build_actions(self) -> None:
        self.add_action = QAction(self._ui_icon("add-file"), "添加文件…", self)
        self.add_action.setShortcut(QKeySequence.StandardKey.Open)
        self.add_action.setToolTip("添加图片或 PDF（Ctrl+O）")
        self.add_action.triggered.connect(self.choose_files)

        self.insert_action = QAction(self._ui_icon("insert-page"), "插入页面…", self)
        self.insert_action.setToolTip("在选中页面前插入文件")
        self.insert_action.triggered.connect(self.choose_insert_files)

        self.delete_action = QAction(self._ui_icon("delete"), "删除", self)
        self.delete_action.setShortcut(QKeySequence.StandardKey.Delete)
        self.delete_action.setToolTip("删除选中页面（Delete，可撤销）")
        self.delete_action.triggered.connect(self.delete_selected)

        self.reset_action = QAction(self._ui_icon("reset"), "重置", self)
        self.reset_action.setToolTip("清空当前工作区（不会删除源文件）")
        self.reset_action.triggered.connect(self.reset_workspace)

        self.undo_action = QAction(self._ui_icon("undo"), "撤销", self)
        self.undo_action.setShortcut(QKeySequence.StandardKey.Undo)
        self.undo_action.triggered.connect(self.undo)
        self.redo_action = QAction(self._ui_icon("redo"), "重做", self)
        self.redo_action.setShortcut(QKeySequence.StandardKey.Redo)
        self.redo_action.triggered.connect(self.redo)

        self.duplicate_action = QAction(self._ui_icon("duplicate"), "复制页面", self)
        self.duplicate_action.setShortcut(QKeySequence("Ctrl+D"))
        self.duplicate_action.triggered.connect(self.duplicate_selected)
        self.rotate_action = QAction(self._ui_icon("rotate-right"), "顺时针旋转", self)
        self.rotate_action.setShortcut(QKeySequence("Ctrl+R"))
        self.rotate_action.triggered.connect(self.rotate_selected)
        self.rotate_left_action = QAction(self._ui_icon("rotate-left"), "向左旋转 90°", self)
        self.rotate_left_action.triggered.connect(lambda: self.rotate_selected_degrees(-90))
        self.move_left_action = QAction("向左移动", self)
        self.move_left_action.setShortcut(QKeySequence("Alt+Left"))
        self.move_left_action.triggered.connect(lambda: self.move_selected(-1))
        self.move_right_action = QAction("向右移动", self)
        self.move_right_action.setShortcut(QKeySequence("Alt+Right"))
        self.move_right_action.triggered.connect(lambda: self.move_selected(1))
        self.export_action = QAction(self._ui_icon("export"), "导出", self)
        self.export_action.setShortcut(QKeySequence.StandardKey.SaveAs)
        self.export_action.setToolTip("导出新 PDF（Ctrl+Shift+S）")
        self.export_action.triggered.connect(self.start_export)

        self.export_selected_action = QAction("导出选中页面…", self)
        self.export_selected_action.setShortcut(QKeySequence("Ctrl+Alt+S"))
        self.export_selected_action.setToolTip("将选中的页面按当前顺序拆分为新 PDF")
        self.export_selected_action.triggered.connect(self.export_selected_pages)

    def _build_menu(self) -> None:
        file_menu = self.menuBar().addMenu("文件")
        file_menu.addAction(self.add_action)
        file_menu.addAction(self.insert_action)
        file_menu.addSeparator()
        file_menu.addAction(self.export_action)
        file_menu.addAction(self.export_selected_action)
        file_menu.addSeparator()
        file_menu.addAction(self.reset_action)
        file_menu.addSeparator()
        file_menu.addAction("退出", self.close, QKeySequence.StandardKey.Quit)
        edit_menu = self.menuBar().addMenu("编辑")
        edit_menu.addAction(self.undo_action)
        edit_menu.addAction(self.redo_action)
        edit_menu.addSeparator()
        edit_menu.addAction(self.duplicate_action)
        edit_menu.addAction(self.rotate_action)
        edit_menu.addAction(self.rotate_left_action)
        edit_menu.addAction(self.move_left_action)
        edit_menu.addAction(self.move_right_action)
        edit_menu.addAction(self.delete_action)
        view_menu = self.menuBar().addMenu("显示")
        theme_group = QActionGroup(self)
        theme_group.setExclusive(True)
        self.light_theme_action = view_menu.addAction("浅色外观")
        self.dark_theme_action = view_menu.addAction("深色外观")
        for action in (self.light_theme_action, self.dark_theme_action):
            action.setCheckable(True)
            theme_group.addAction(action)
        self.light_theme_action.setChecked(True)
        self.light_theme_action.triggered.connect(lambda: apply_theme(QApplication.instance(), False))
        self.dark_theme_action.triggered.connect(lambda: apply_theme(QApplication.instance(), True))
        feedback_menu = self.menuBar().addMenu("反馈")
        self.author_email_action = feedback_menu.addAction("作者邮箱：577291451@qq.com")
        self.author_email_action.setToolTip("点击复制作者邮箱")
        self.author_email_action.triggered.connect(self.copy_author_email)

    def copy_author_email(self) -> None:
        QApplication.clipboard().setText("577291451@qq.com")
        self.statusBar().showMessage("作者邮箱已复制：577291451@qq.com", 4000)

    def _build_toolbar(self) -> None:
        toolbar = QToolBar("主要工具", self)
        toolbar.setMovable(False)
        toolbar.setIconSize(QSize(20, 20))
        toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.addToolBar(toolbar)
        toolbar.addAction(self.add_action)
        toolbar.addAction(self.insert_action)
        toolbar.addAction(self.reset_action)
        toolbar.addSeparator()
        toolbar.addAction(self.delete_action)
        toolbar.addAction(self.undo_action)
        toolbar.addAction(self.redo_action)

    def _build_content(self) -> None:
        root = QWidget(objectName="Root")
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setChildrenCollapsible(False)
        root_layout.addWidget(self.splitter)
        self.splitter.addWidget(self._create_sidebar())
        self.splitter.addWidget(self._create_workspace())
        self.splitter.addWidget(self._create_inspector())
        self.splitter.setSizes([210, 750, 400])
        self.splitter.setStretchFactor(1, 1)
        self.setCentralWidget(root)

    def _create_sidebar(self) -> QWidget:
        panel = QWidget(objectName="Sidebar")
        panel.setMinimumWidth(170)
        panel.setMaximumWidth(300)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(14, 18, 12, 14)
        title = QLabel("文件与页面", objectName="PanelTitle")
        layout.addWidget(title)
        self.source_list = SourceList()
        self.source_list.setAccessibleName("已导入文件")
        self.source_list.remove_requested.connect(self.delete_source_file)
        layout.addWidget(self.source_list, 1)
        summary = QLabel("尚未添加文件", objectName="Secondary")
        summary.setWordWrap(True)
        self.source_summary = summary
        layout.addWidget(summary)
        return panel

    def _create_workspace(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        header = QWidget()
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(22, 10, 32, 6)
        self.workspace_title = QLabel("页面", objectName="PanelTitle")
        header_layout.addWidget(self.workspace_title)
        header_layout.addStretch()
        small = QLabel("缩略图", objectName="Secondary")
        header_layout.addWidget(small)
        self.zoom_slider = TactileSlider(Qt.Orientation.Horizontal)
        self.zoom_slider.setRange(110, 230)
        self.zoom_slider.setValue(self.thumbnail_size)
        self.zoom_slider.setFixedSize(170, 34)
        self.zoom_slider.setAccessibleName("缩略图大小")
        self.zoom_slider.valueChanged.connect(self.set_thumbnail_size)
        header_layout.addWidget(self.zoom_slider)
        layout.addWidget(header)

        stack = QFrame()
        stack.setObjectName("PageStack")
        self.page_stack = stack
        stack.installEventFilter(self)
        stack_layout = QVBoxLayout(stack)
        stack_layout.setContentsMargins(0, 0, 0, 0)
        self.page_grid = PageGrid()
        self.page_grid.delete_requested.connect(self.delete_selected)
        self.page_grid.files_dropped.connect(self.add_files)
        self.page_grid.order_changed.connect(self.apply_grid_order)
        self.page_grid.open_preview_requested.connect(self.show_preview)
        self.page_grid.rotate_page_requested.connect(self.rotate_page)
        self.page_grid.context_menu_requested.connect(self.show_page_context_menu)
        self.page_grid.itemSelectionChanged.connect(self._selection_changed)
        self.page_grid.itemChanged.connect(self._image_check_changed)
        stack_layout.addWidget(self.page_grid)
        self.empty_state = self._create_empty_state(stack)
        self.empty_state.raise_()
        self.workspace_stack = QStackedWidget()
        self.workspace_stack.addWidget(stack)
        self.batch_empty_state = QWidget(objectName="EmptyState")
        batch_empty_layout = QVBoxLayout(self.batch_empty_state)
        batch_empty_layout.setContentsMargins(24, 24, 24, 24)
        batch_empty_layout.addStretch()
        self.batch_brand_logo = self._brand_logo_label(112)
        batch_empty_layout.addWidget(self.batch_brand_logo)
        batch_title = QLabel("添加需要独立压缩的 PDF 文件", objectName="EmptyTitle")
        batch_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.batch_empty_title = batch_title
        batch_empty_layout.addWidget(batch_title)
        batch_hint = QLabel("每个 PDF 将生成一个独立输出文件", objectName="EmptyHint")
        batch_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        batch_empty_layout.addWidget(batch_hint)
        add_batch = QPushButton("添加 PDF 文件")
        add_batch.setObjectName("PrimaryButton")
        add_batch.clicked.connect(self.choose_batch_files)
        batch_button_row = QHBoxLayout()
        batch_button_row.addStretch()
        batch_button_row.addWidget(add_batch)
        batch_button_row.addStretch()
        batch_empty_layout.addLayout(batch_button_row)
        self.batch_list = QListWidget()
        self.batch_list.setVisible(False)
        batch_empty_layout.addWidget(self.batch_list, 1)
        self.batch_remove_button = QPushButton("移除选中文件")
        self.batch_remove_button.clicked.connect(self.remove_batch_files)
        self.batch_remove_button.setVisible(False)
        batch_empty_layout.addWidget(self.batch_remove_button)
        batch_empty_layout.addStretch()
        self.workspace_stack.addWidget(self.batch_empty_state)
        layout.addWidget(self.workspace_stack, 1)
        self.move_controls = QWidget()
        move_layout = QHBoxLayout(self.move_controls)
        move_layout.setContentsMargins(22, 4, 22, 10)
        self.selection_summary = QLabel("", objectName="Secondary")
        move_layout.addWidget(self.selection_summary)
        move_layout.addStretch()
        self.move_left_button = QPushButton("← 向左移动")
        self.move_left_button.setToolTip("将选中页面向前移动一位（Alt+←）")
        self.move_left_button.clicked.connect(self.move_left_action.trigger)
        move_layout.addWidget(self.move_left_button)
        self.move_right_button = QPushButton("向右移动 →")
        self.move_right_button.setToolTip("将选中页面向后移动一位（Alt+→）")
        self.move_right_button.clicked.connect(self.move_right_action.trigger)
        move_layout.addWidget(self.move_right_button)
        self.move_controls.setVisible(False)
        layout.addWidget(self.move_controls)
        return panel

    def _create_empty_state(self, parent: QWidget) -> QWidget:
        empty = QWidget(parent, objectName="EmptyState")
        empty.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        outer = QVBoxLayout(empty)
        outer.addStretch()
        outer.addWidget(self._brand_logo_label(112))
        title = QLabel("拖入图片或 PDF 文件", objectName="EmptyTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        outer.addWidget(title)
        hint = QLabel("文件仅在本机处理", objectName="EmptyHint")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        outer.addWidget(hint)
        choose = QPushButton("选择文件")
        choose.setObjectName("PrimaryButton")
        choose.setFixedWidth(112)
        choose.clicked.connect(self.choose_files)
        row = QHBoxLayout()
        row.addStretch()
        row.addWidget(choose)
        row.addStretch()
        outer.addLayout(row)
        outer.addStretch()
        return empty

    @staticmethod
    def _brand_logo_label(size: int) -> QLabel:
        icon = QLabel(objectName="BrandLogo")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        brand_logo = ui_resource_path("assets/branding/pdf-toaster-app-512.png")
        icon.setPixmap(
            QPixmap(str(brand_logo)).scaled(
                size,
                size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
        icon.setAccessibleName("PDF Studio Lite 烤面包机图标")
        icon.setFixedHeight(size)
        return icon

    def eventFilter(self, watched, event) -> bool:  # type: ignore[no-untyped-def]
        if hasattr(self, "page_stack") and watched is self.page_stack and event.type() == QEvent.Type.Resize:
            if hasattr(self, "empty_state"):
                self.empty_state.setGeometry(self.page_stack.rect())
                self.empty_state.raise_()
        return super().eventFilter(watched, event)

    def resizeEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        super().resizeEvent(event)
        if hasattr(self, "empty_state"):
            self.empty_state.setGeometry(self.page_stack.rect())

    def _create_inspector(self) -> QWidget:
        panel = QWidget(objectName="Inspector")
        panel.setMinimumWidth(370)
        panel.setMaximumWidth(460)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(16, 18, 16, 14)
        layout.setSpacing(12)
        self.mode_selector = SegmentedTabBar()
        self.mode_selector.addTab("PDF")
        self.mode_selector.addTab("图片")
        self.mode_selector.addTab("压缩")
        self.mode_selector.addTab("水印")
        self.mode_selector.currentChanged.connect(self.set_workspace_mode)
        layout.addWidget(self.mode_selector)
        self.inspector_title = QLabel("导出为 PDF", objectName="PanelTitle")
        layout.addWidget(self.inspector_title)
        self.inspector_stack = QStackedWidget()
        pdf_content = QWidget(objectName="PdfInspectorContent")
        pdf_layout = QVBoxLayout(pdf_content)
        pdf_layout.setContentsMargins(0, 0, 0, 0)
        pdf_layout.setSpacing(12)
        form = QFormLayout()
        form.setVerticalSpacing(10)
        desktop = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DesktopLocation)
        self.output_dir = QLineEdit(desktop or str(Path.home() / "Desktop"))
        browse = QPushButton("选择…")
        browse.clicked.connect(self.choose_output_dir)
        path_row = QHBoxLayout()
        path_row.addWidget(self.output_dir, 1)
        path_row.addWidget(browse)
        form.addRow("输出位置", path_row)
        self.filename = QLineEdit("PDF Studio Lite 输出.pdf")
        form.addRow("文件名", self.filename)
        pdf_layout.addLayout(form)

        quality_hint = QLabel("默认保留原页面；图片按原始像素尺寸生成。", objectName="Secondary")
        quality_hint.setWordWrap(True)
        pdf_layout.addWidget(quality_hint)
        self.compress_checkbox = LabeledSwitch("压缩文件大小")
        self.compress_checkbox.setToolTip("开启后自动搜索接近目标大小的最高质量结果")
        self.compress_checkbox.toggled.connect(self._toggle_target_controls)
        pdf_layout.addWidget(self.compress_checkbox)
        self.target_controls = QWidget()
        target_layout = QVBoxLayout(self.target_controls)
        target_layout.setContentsMargins(0, 0, 0, 0)
        target_row = QHBoxLayout()
        self.target_value = QDoubleSpinBox()
        self.target_value.setRange(0.1, 10240.0)
        self.target_value.setDecimals(1)
        self.target_value.setSingleStep(0.5)
        self.target_value.setValue(3.0)
        self.target_unit = QComboBox()
        self.target_unit.addItems(["MB", "KB"])
        self.target_value.valueChanged.connect(self._update_target_label)
        self.target_unit.currentTextChanged.connect(self._update_target_label)
        target_row.addWidget(self.target_value, 1)
        target_row.addWidget(self.target_unit)
        target_layout.addLayout(target_row)
        target_hint = QLabel("以不超过目标为优先；误差要求不超过 0.5 MB。", objectName="Secondary")
        target_hint.setWordWrap(True)
        target_layout.addWidget(target_hint)
        pdf_layout.addWidget(self.target_controls)

        self.batch_rotate_checkbox = LabeledSwitch("批量旋转页面")
        pdf_layout.addWidget(self.batch_rotate_checkbox)
        self.batch_rotate_controls = QWidget()
        rotate_row = QHBoxLayout(self.batch_rotate_controls)
        rotate_row.setContentsMargins(0, 0, 0, 0)
        rotate_left = QPushButton("↶ 左旋转 90°")
        rotate_right = QPushButton("↷ 右旋转 90°")
        rotate_left.clicked.connect(lambda: self.rotate_all_pages(-90))
        rotate_right.clicked.connect(lambda: self.rotate_all_pages(90))
        rotate_row.addWidget(rotate_left)
        rotate_row.addWidget(rotate_right)
        self.batch_rotate_checkbox.toggled.connect(self.batch_rotate_controls.setVisible)
        self.batch_rotate_controls.setVisible(False)
        pdf_layout.addWidget(self.batch_rotate_controls)

        self.uniform_size_checkbox = LabeledSwitch("统一页面尺寸")
        pdf_layout.addWidget(self.uniform_size_checkbox)
        self.uniform_size_controls = QWidget()
        size_form = QFormLayout(self.uniform_size_controls)
        size_form.setContentsMargins(0, 0, 0, 0)
        self.page_size_combo = QComboBox()
        self.page_size_combo.addItems(PAGE_SIZES_MM)
        self.page_size_combo.setCurrentText("A4 — 210 × 297 mm")
        self.page_orientation_combo = QComboBox()
        self.page_orientation_combo.addItems(["自动适配", "纵向", "横向"])
        self.page_fit_combo = QComboBox()
        self.page_fit_combo.addItems(["等比例完整适配", "等比例填满并裁切"])
        size_form.addRow("页面尺寸", self.page_size_combo)
        size_form.addRow("页面方向", self.page_orientation_combo)
        size_form.addRow("内容适配", self.page_fit_combo)
        self.uniform_size_checkbox.toggled.connect(self.uniform_size_controls.setVisible)
        self.uniform_size_controls.setVisible(False)
        pdf_layout.addWidget(self.uniform_size_controls)

        self.gap_checkbox = LabeledSwitch("增加页间空白")
        self.gap_checkbox.setToolTip("在除最后一页外的页面底部写入空白区域；阅读器自身间距不受控制")
        pdf_layout.addWidget(self.gap_checkbox)
        self.gap_controls = QWidget()
        gap_row = QHBoxLayout(self.gap_controls)
        gap_row.setContentsMargins(0, 0, 0, 0)
        self.gap_value = QDoubleSpinBox()
        self.gap_value.setRange(0.5, 50.0)
        self.gap_value.setDecimals(1)
        self.gap_value.setSingleStep(0.5)
        self.gap_value.setValue(5.0)
        self.gap_value.setSuffix(" mm")
        self.gap_value.setToolTip("常用文档建议从 3–10 mm 开始")
        gap_row.addWidget(QLabel("间距"))
        gap_row.addWidget(self.gap_value, 1)
        self.gap_checkbox.toggled.connect(self.gap_controls.setVisible)
        pdf_layout.addWidget(self.gap_controls)
        self.gap_controls.setVisible(False)

        info = QFormLayout()
        self.current_size = QLabel("—", objectName="Secondary")
        self.target_size_label = QLabel("—", objectName="Secondary")
        self.actual_size = QLabel("—", objectName="Secondary")
        self.ratio_label = QLabel("—", objectName="Secondary")
        self.error_label = QLabel("—", objectName="Secondary")
        info.addRow("当前文件大小", self.current_size)
        info.addRow("目标文件大小", self.target_size_label)
        self.target_size_caption = info.labelForField(self.target_size_label)
        info.addRow("实际输出大小", self.actual_size)
        info.addRow("压缩率", self.ratio_label)
        info.addRow("目标误差", self.error_label)
        pdf_layout.addLayout(info)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        pdf_layout.addWidget(self.progress)
        self.progress_text = QLabel("就绪", objectName="Secondary")
        self.progress_text.setWordWrap(True)
        pdf_layout.addWidget(self.progress_text)
        pdf_layout.addStretch()
        self.cancel_button = QPushButton("取消任务")
        self.cancel_button.setVisible(False)
        self.cancel_button.clicked.connect(self.cancel_task)
        pdf_layout.addWidget(self.cancel_button)
        self.export_button = QPushButton("导出 PDF")
        self.export_button.setObjectName("PrimaryButton")
        self.export_button.clicked.connect(self.start_export)
        pdf_layout.addWidget(self.export_button)
        pdf_page = QScrollArea(objectName="InspectorScroll")
        pdf_page.setWidgetResizable(True)
        pdf_page.setFrameShape(QScrollArea.Shape.NoFrame)
        pdf_page.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        pdf_page.setWidget(pdf_content)
        self.pdf_inspector_scroll = pdf_page
        self.inspector_stack.addWidget(pdf_page)
        self.inspector_stack.addWidget(self._create_image_inspector())
        self.inspector_stack.addWidget(self._create_batch_inspector())
        self.watermark_panel = WatermarkPanel()
        self.watermark_panel.preview_changed.connect(self.schedule_watermark_preview)
        self.watermark_panel.apply_requested.connect(self.start_watermark_export)
        self.watermark_panel.scan_requested.connect(self.start_watermark_scan)
        self.watermark_panel.remove_requested.connect(self.start_watermark_removal)
        self.watermark_panel.detection_list.itemChanged.connect(
            lambda *_: self.watermark_panel.remove_button.setEnabled(
                self.active_task is None and bool(self.watermark_panel.checked_removal_ids())
            )
        )
        self.inspector_stack.addWidget(self.watermark_panel)
        layout.addWidget(self.inspector_stack, 1)
        self._update_target_label()
        self._toggle_target_controls(False)
        return panel

    @staticmethod
    def _create_mode_placeholder(title: str, description: str) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 8, 0, 0)
        heading = QLabel(title, objectName="SectionTitle")
        layout.addWidget(heading)
        detail = QLabel(description, objectName="Secondary")
        detail.setWordWrap(True)
        layout.addWidget(detail)
        layout.addStretch()
        return page

    def _create_image_inspector(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        form = QFormLayout()
        desktop = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DesktopLocation)
        self.image_output_dir = QLineEdit(desktop or str(Path.home() / "Desktop"))
        choose = QPushButton("选择…")
        choose.clicked.connect(self.choose_image_output_dir)
        output_row = QHBoxLayout()
        output_row.addWidget(self.image_output_dir, 1)
        output_row.addWidget(choose)
        form.addRow("输出文件夹", output_row)
        self.image_prefix = QLineEdit("页面")
        form.addRow("文件名前缀", self.image_prefix)
        self.image_format = QComboBox()
        self.image_format.addItems(["PNG", "JPG", "WebP", "TIFF"])
        form.addRow("图片格式", self.image_format)
        self.image_dpi = QComboBox()
        self.image_dpi.addItems(["原图", "96 DPI", "150 DPI", "200 DPI", "300 DPI"])
        self.image_dpi.setCurrentText("200 DPI")
        form.addRow("清晰度", self.image_dpi)
        self.image_quality = QSpinBox()
        self.image_quality.setRange(1, 100)
        self.image_quality.setValue(90)
        form.addRow("质量", self.image_quality)
        self.image_merge_long = LabeledSwitch("合并为长图输出")
        self.image_merge_long.setToolTip("按当前页面顺序纵向拼接，只输出一张图片；默认关闭。")
        form.addRow("输出方式", self.image_merge_long)
        self.image_format.currentTextChanged.connect(self._update_image_quality_control)
        self.image_dpi.currentTextChanged.connect(self._update_image_quality_control)
        layout.addLayout(form)
        self.image_original_hint = QLabel(
            "原图：图片保持上传时的原始像素尺寸，不放大；使用无损压缩避免文件异常膨胀。PDF 页面以 600 DPI 渲染。",
            objectName="Secondary",
        )
        self.image_original_hint.setWordWrap(True)
        self.image_original_hint.setVisible(False)
        layout.addWidget(self.image_original_hint)
        buttons = QHBoxLayout()
        select_all = QPushButton("全选")
        select_none = QPushButton("取消全选")
        select_all.clicked.connect(lambda: self.set_all_image_checks(True))
        select_none.clicked.connect(lambda: self.set_all_image_checks(False))
        buttons.addWidget(select_all)
        buttons.addWidget(select_none)
        layout.addLayout(buttons)
        self.image_selection_label = QLabel("已选择 0 页", objectName="Secondary")
        layout.addWidget(self.image_selection_label)
        self.image_progress = QProgressBar()
        self.image_progress.setRange(0, 100)
        self.image_progress.setValue(0)
        layout.addWidget(self.image_progress)
        self.image_progress_text = QLabel("就绪", objectName="Secondary")
        layout.addWidget(self.image_progress_text)
        layout.addStretch()
        self.image_cancel_button = QPushButton("取消任务")
        self.image_cancel_button.clicked.connect(self.cancel_task)
        self.image_cancel_button.setVisible(False)
        layout.addWidget(self.image_cancel_button)
        self.image_export_button = QPushButton("导出图片")
        self.image_export_button.setObjectName("PrimaryButton")
        self.image_export_button.clicked.connect(self.start_image_export)
        layout.addWidget(self.image_export_button)
        self.image_quality.setVisible(False)
        return page

    def _update_image_quality_control(self) -> None:
        original = self.image_dpi.currentText() == "原图"
        self.image_quality.setVisible(
            not original and self.image_format.currentText().upper() in {"JPG", "WEBP"}
        )
        self.image_original_hint.setVisible(original)

    def _create_batch_inspector(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        form = QFormLayout()
        desktop = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DesktopLocation)
        self.batch_output_dir = QLineEdit(desktop or str(Path.home() / "Desktop"))
        choose = QPushButton("选择…")
        choose.clicked.connect(self.choose_batch_output_dir)
        row = QHBoxLayout()
        row.addWidget(self.batch_output_dir, 1)
        row.addWidget(choose)
        form.addRow("输出文件夹", row)
        layout.addLayout(form)
        self.batch_target_checkbox = LabeledSwitch("启用目标文件大小")
        layout.addWidget(self.batch_target_checkbox)
        self.batch_target_controls = QWidget()
        target_row = QHBoxLayout(self.batch_target_controls)
        target_row.setContentsMargins(0, 0, 0, 0)
        self.batch_target_value = QDoubleSpinBox()
        self.batch_target_value.setRange(0.1, 10240)
        self.batch_target_value.setValue(3.0)
        self.batch_target_unit = QComboBox()
        self.batch_target_unit.addItems(["MB", "KB"])
        target_row.addWidget(self.batch_target_value, 1)
        target_row.addWidget(self.batch_target_unit)
        self.batch_target_checkbox.toggled.connect(self.batch_target_controls.setVisible)
        self.batch_target_controls.setVisible(False)
        layout.addWidget(self.batch_target_controls)
        self.batch_progress = QProgressBar()
        layout.addWidget(self.batch_progress)
        self.batch_status = QLabel("尚未添加 PDF", objectName="Secondary")
        self.batch_status.setWordWrap(True)
        layout.addWidget(self.batch_status)
        layout.addStretch()
        self.batch_cancel_button = QPushButton("取消任务")
        self.batch_cancel_button.clicked.connect(self.cancel_task)
        self.batch_cancel_button.setVisible(False)
        layout.addWidget(self.batch_cancel_button)
        self.batch_start_button = QPushButton("开始批量压缩")
        self.batch_start_button.setObjectName("PrimaryButton")
        self.batch_start_button.clicked.connect(self.start_batch_compression)
        self.batch_start_button.setEnabled(False)
        layout.addWidget(self.batch_start_button)
        return page

    def set_workspace_mode(self, index: int) -> None:
        self.workspace_mode = WorkspaceMode(index)
        self.inspector_stack.setCurrentIndex(index)
        is_batch = self.workspace_mode == WorkspaceMode.BATCH
        self.workspace_stack.setCurrentIndex(1 if is_batch else 0)
        self.move_controls.setVisible(not is_batch and bool(self.selected_rows()))
        titles = {
            WorkspaceMode.PDF: "导出为 PDF",
            WorkspaceMode.IMAGES: "导出为图片",
            WorkspaceMode.BATCH: "批量压缩 PDF",
            WorkspaceMode.WATERMARK: "水印管理",
        }
        self.inspector_title.setText(titles[self.workspace_mode])
        self.workspace_title.setText("批量压缩 PDF" if is_batch else f"页面  {len(self.model.pages)}")
        self._apply_image_checkboxes()
        if self.workspace_mode == WorkspaceMode.WATERMARK:
            self.schedule_watermark_preview()
        else:
            self.watermark_preview_asset = None
            self._repaint_cached_thumbnails()
        self._update_actions()

    def choose_image_output_dir(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "选择图片输出文件夹", self.image_output_dir.text())
        if folder:
            self.image_output_dir.setText(folder)

    def _apply_image_checkboxes(self) -> None:
        if not hasattr(self, "page_grid"):
            return
        self.page_grid.blockSignals(True)
        try:
            for row in range(self.page_grid.count()):
                item = self.page_grid.item(row)
                uid = item.data(Qt.ItemDataRole.UserRole)
                if self.workspace_mode == WorkspaceMode.IMAGES:
                    item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                    item.setCheckState(Qt.CheckState.Checked if uid in self.image_checked_uids else Qt.CheckState.Unchecked)
                else:
                    item.setData(Qt.ItemDataRole.CheckStateRole, None)
        finally:
            self.page_grid.blockSignals(False)
        self._update_image_selection_label()

    def _image_check_changed(self, item: QListWidgetItem) -> None:
        if self.workspace_mode != WorkspaceMode.IMAGES:
            return
        uid = item.data(Qt.ItemDataRole.UserRole)
        if item.checkState() == Qt.CheckState.Checked:
            self.image_checked_uids.add(uid)
        else:
            self.image_checked_uids.discard(uid)
        self._update_image_selection_label()

    def set_all_image_checks(self, checked: bool) -> None:
        self.image_checked_uids = {
            self.page_grid.item(row).data(Qt.ItemDataRole.UserRole) for row in range(self.page_grid.count())
        } if checked else set()
        self._apply_image_checkboxes()

    def _update_image_selection_label(self) -> None:
        if hasattr(self, "image_selection_label"):
            count = sum(page.uid in self.image_checked_uids for page in self.model.pages)
            self.image_selection_label.setText(f"已选择 {count} 页")
            self.image_export_button.setEnabled(count > 0 and self.active_task is None)

    def start_image_export(self) -> None:
        pages = tuple(page for page in self.model.pages if page.uid in self.image_checked_uids)
        if not pages or self.active_task:
            return
        dpi_text = self.image_dpi.currentText()
        dpi = None if dpi_text == "原图" else int(dpi_text.split()[0])
        def work(*, progress, cancelled):  # type: ignore[no-untyped-def]
            return export_page_images(
                pages,
                self.image_output_dir.text(),
                self.image_prefix.text().strip() or "页面",
                self.image_format.currentText(),
                dpi,
                self.image_quality.value(),
                self.image_merge_long.isChecked(),
                progress,
                cancelled,
            )
        self.active_task = FunctionTask(work)
        self.active_task.signals.progress.connect(self._task_progress)
        self.active_task.signals.result.connect(self._image_export_complete)
        self.active_task.signals.error.connect(lambda error: self.show_error("图片导出失败", error))
        self.active_task.signals.finished.connect(self._task_finished)
        self.cancel_button.setVisible(True)
        self.image_cancel_button.setVisible(True)
        self.pool.start(self.active_task)

    def _image_export_complete(self, result: object) -> None:
        data = result  # type: ignore[assignment]
        outputs = data["outputs"]
        failures = data["failures"]
        self.progress.setValue(100)
        self.image_progress.setValue(100)
        QMessageBox.information(
            self,
            "图片导出完成",
            f"成功：{data.get('exported_pages', len(outputs))} 页\n"
            f"输出文件：{len(outputs)} 个{'（长图）' if data.get('merged') else ''}\n"
            f"失败：{len(failures)} 页\n输出目录：{data['output_dir']}",
        )

    def _selection_changed(self) -> None:
        self._update_actions()
        if self.workspace_mode == WorkspaceMode.WATERMARK:
            self.schedule_watermark_preview()

    def schedule_watermark_preview(self) -> None:
        if self.workspace_mode == WorkspaceMode.WATERMARK:
            self.watermark_preview_timer.start()

    def refresh_watermark_preview(self) -> None:
        if self.workspace_mode != WorkspaceMode.WATERMARK:
            return
        try:
            spec = self.watermark_panel.spec()
            self.watermark_preview_asset = render_watermark_asset(
                spec,
                self.watermark_panel.image_path.text().strip() or None,
            )
            self.watermark_panel.status.setText("预览已更新；应用前不会修改任何源文件。")
        except Exception as error:
            self.watermark_preview_asset = None
            self.watermark_panel.status.setText(str(error))
        self._repaint_cached_thumbnails()

    def _repaint_cached_thumbnails(self) -> None:
        for uid, data in tuple(self.thumbnail_cache.items()):
            self._apply_thumbnail((uid, data))

    def _watermark_preview_pages(self) -> set[int]:
        try:
            return set(self.watermark_panel.selected_pages(len(self.model.pages), self.selected_rows()))
        except ValueError:
            return set()

    def start_watermark_export(self) -> None:
        if not self.model.pages or self.active_task:
            QMessageBox.warning(self, "无法添加水印", "请先添加 PDF 或图片页面。")
            return
        try:
            spec = self.watermark_panel.spec()
            asset = render_watermark_asset(spec, self.watermark_panel.image_path.text().strip() or None)
            page_indices = self.watermark_panel.selected_pages(len(self.model.pages), self.selected_rows())
            destination = self.watermark_panel.output_path()
        except Exception as error:
            self.show_error("水印参数无效", str(error))
            return
        if destination.exists():
            answer = QMessageBox.question(self, "替换现有文件？", f"{destination.name} 已存在。要替换它吗？")
            if answer != QMessageBox.StandardButton.Yes:
                return
        pages = tuple(self.model.pages)

        def work(*, progress, cancelled):  # type: ignore[no-untyped-def]
            intermediate = destination.with_name(f".{destination.stem}.watermark-source.pdf")
            try:
                export_pages(
                    pages,
                    intermediate,
                    lambda current, total: progress(current, max(total, 1) * 4, "正在准备 PDF 页面…"),
                    cancelled,
                )
                record = apply_watermark(
                    intermediate,
                    destination,
                    asset,
                    spec,
                    page_indices,
                    progress=lambda current, total, message: progress(total * 4 + current, total * 5, message),
                    cancelled=cancelled,
                )
                return {"path": destination, "record": record}
            finally:
                intermediate.unlink(missing_ok=True)

        self.active_task = FunctionTask(work)
        self.active_task.signals.progress.connect(self._task_progress)
        self.active_task.signals.result.connect(self._watermark_export_complete)
        self.active_task.signals.error.connect(lambda error: self.show_error("水印导出失败", error))
        self.active_task.signals.finished.connect(self._task_finished)
        self.watermark_panel.set_busy(True)
        self.watermark_panel.status.setText("正在准备水印导出…")
        self.pool.start(self.active_task)

    def _watermark_export_complete(self, result: object) -> None:
        data = result  # type: ignore[assignment]
        path: Path = data["path"]
        record: WatermarkRecord = data["record"]
        self.watermark_panel.status.setText(
            f"已导出 {len(record.pages)} 页 · 可追踪标识 {record.watermark_id[:8]}…"
        )
        self.statusBar().showMessage(f"水印 PDF 已导出：{path}", 10000)
        ExportResultDialog(path, None, self).exec()

    def start_watermark_scan(self) -> None:
        source = Path(self.watermark_panel.remove_source.text().strip())
        if not source.is_file() or source.suffix.lower() != ".pdf":
            QMessageBox.warning(self, "无法扫描", "请先选择有效的 PDF 文件。")
            return
        source = source.resolve()
        if self.active_task:
            self.pending_watermark_scan = source
            self.watermark_panel.remove_status.setText("后台任务结束后将自动扫描当前 PDF…")
            return
        self.pending_watermark_scan = None

        def work(*, progress, cancelled):  # type: ignore[no-untyped-def]
            progress(0, 1, "正在扫描可追踪水印对象…")
            if cancelled():
                return {"source": source, "records": []}
            records = scan_watermarks(source)
            progress(1, 1, "扫描完成")
            return {"source": source, "records": records}

        self.active_task = FunctionTask(work)
        self.active_task.signals.progress.connect(self._task_progress)
        self.active_task.signals.result.connect(self._watermark_scan_complete)
        self.active_task.signals.error.connect(lambda error: self.show_error("水印扫描失败", error))
        self.active_task.signals.finished.connect(self._task_finished)
        self.watermark_panel.set_busy(True)
        self.pool.start(self.active_task)

    def _watermark_scan_complete(self, result: object) -> None:
        data = result  # type: ignore[assignment]
        source = Path(data["source"])
        current_source = Path(self.watermark_panel.remove_source.text().strip()).resolve()
        if source != current_source:
            return
        records: list[WatermarkRecord] = data["records"]
        self.watermark_panel.detection_list.clear()
        for record in records:
            pages = "、".join(str(page) for page in record.pages)
            status = "可安全移除" if record.removable else "暂不支持安全删除"
            item = QListWidgetItem(f"{status} · {record.label}\n页面：{pages} · 判断依据见提示")
            item.setData(Qt.ItemDataRole.UserRole, record.watermark_id if record.removable else None)
            item.setToolTip(record.reason)
            if record.removable:
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(Qt.CheckState.Checked)
            else:
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEnabled)
            self.watermark_panel.detection_list.addItem(item)
        removable = sum(record.removable for record in records)
        if records:
            self.watermark_panel.remove_status.setText(f"检测到 {len(records)} 项，其中 {removable} 项支持安全移除。")
            self.watermark_panel.remove_button.setEnabled(removable > 0)
        else:
            self.watermark_panel.remove_status.setText(
                "未检测到本软件的可追踪水印。复杂、扫描件或与正文合并的水印不会被强行删除。"
            )

    def start_watermark_removal(self) -> None:
        if self.active_task:
            return
        source = Path(self.watermark_panel.remove_source.text().strip())
        destination = Path(self.watermark_panel.remove_output.text().strip())
        selected = self.watermark_panel.checked_removal_ids()
        if not selected:
            QMessageBox.warning(self, "没有选择水印", "请勾选需要安全移除的水印对象。")
            return
        answer = QMessageBox.question(
            self,
            "确认移除水印？",
            "只会移除带 PDF Studio Lite 可追踪标识的独立水印流。原文件不会修改，是否继续？",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        if destination.exists():
            answer = QMessageBox.question(self, "替换现有文件？", f"{destination.name} 已存在。要替换它吗？")
            if answer != QMessageBox.StandardButton.Yes:
                return

        def work(*, progress, cancelled):  # type: ignore[no-untyped-def]
            removed = remove_watermarks(source, destination, selected, progress=progress, cancelled=cancelled)
            return {"path": destination, "removed": removed}

        self.active_task = FunctionTask(work)
        self.active_task.signals.progress.connect(self._task_progress)
        self.active_task.signals.result.connect(self._watermark_removal_complete)
        self.active_task.signals.error.connect(lambda error: self.show_error("移除水印失败", error))
        self.active_task.signals.finished.connect(self._task_finished)
        self.watermark_panel.set_busy(True)
        self.pool.start(self.active_task)

    def _watermark_removal_complete(self, result: object) -> None:
        data = result  # type: ignore[assignment]
        path: Path = data["path"]
        removed: tuple[WatermarkRecord, ...] = data["removed"]
        self.watermark_panel.remove_status.setText(f"已安全移除 {len(removed)} 组水印，原文件保持不变。")
        self.statusBar().showMessage(f"无水印 PDF 已导出：{path}", 10000)
        ExportResultDialog(path, None, self).exec()

    def _build_statusbar(self) -> None:
        status = QStatusBar()
        status.setSizeGripEnabled(True)
        self.setStatusBar(status)
        self.statusBar().showMessage("完全离线 · 原文件只读")

    def choose_files(self) -> None:
        if self.workspace_mode == WorkspaceMode.BATCH:
            self.choose_batch_files()
            return
        paths, _ = QFileDialog.getOpenFileNames(self, "添加图片或 PDF", "", FILE_FILTER)
        if paths:
            self.add_files(paths, self.page_grid.count())

    def choose_insert_files(self) -> None:
        selected = self.selected_rows()
        position = min(selected) if selected else self.page_grid.count()
        paths, _ = QFileDialog.getOpenFileNames(self, "插入图片或 PDF", "", FILE_FILTER)
        if paths:
            self.add_files(paths, position)

    def add_files(self, paths: list[str], position: int) -> None:
        if self.workspace_mode == WorkspaceMode.BATCH:
            self.add_batch_files(paths)
            return
        try:
            was_empty = not self.model.pages
            imported = self.model.add_files(paths, position)
            if was_empty:
                first_pdf = next((page.source for page in imported if page.source.suffix.lower() == ".pdf"), None)
                if first_pdf is not None:
                    stem = first_pdf.stem
                    if not stem.endswith("_PDFStudioLite"):
                        stem += "_PDFStudioLite"
                    self.filename.setText(f"{stem}.pdf")
                    self.watermark_panel.filename.setText(f"{first_pdf.stem}_水印_PDFStudioLite.pdf")
            warnings: list[str] = []
            for path in {page.source for page in imported if page.source.suffix.lower() == ".pdf"}:
                warnings.extend(inspect_pdf(path).warnings)
            self.refresh_grid()
            imported_pdfs = tuple(dict.fromkeys(page.source.resolve() for page in imported if page.source.suffix.lower() == ".pdf"))
            if self.workspace_mode == WorkspaceMode.WATERMARK and self.watermark_panel.is_remove_mode() and imported_pdfs:
                self.watermark_panel.set_remove_source(imported_pdfs[0], automatic=True)
                QTimer.singleShot(0, self.start_watermark_scan)
            if warnings:
                QMessageBox.warning(self, "PDF 特性提示", "\n".join(dict.fromkeys(warnings)))
            if self.workspace_mode == WorkspaceMode.WATERMARK and self.watermark_panel.is_remove_mode() and imported_pdfs:
                self.statusBar().showMessage(f"已导入 {imported_pdfs[0].name}，正在自动扫描水印", 5000)
            else:
                self.statusBar().showMessage(f"已添加 {len(imported)} 页", 4000)
        except Exception as error:
            self.show_error("无法添加文件", str(error))

    def choose_batch_files(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(self, "添加需要压缩的 PDF", "", "PDF 文件 (*.pdf)")
        self.add_batch_files(paths)

    def add_batch_files(self, paths: list[str]) -> None:
        for raw in paths:
            path = Path(raw).resolve()
            if path.suffix.lower() == ".pdf" and path.exists() and path not in self.batch_files:
                self.batch_files.append(path)
        self.refresh_batch_list()

    def refresh_batch_list(self) -> None:
        self.batch_list.clear()
        for path in self.batch_files:
            try:
                with pymupdf.open(path) as doc:
                    pages = doc.page_count
                self.batch_list.addItem(f"{path.name}    {pages} 页    {self.format_size(path.stat().st_size)}")
            except Exception:
                self.batch_list.addItem(f"{path.name}    无法读取")
        has_files = bool(self.batch_files)
        self.batch_list.setVisible(has_files)
        self.batch_remove_button.setVisible(has_files)
        self.batch_start_button.setEnabled(has_files and self.active_task is None)
        self.batch_status.setText(f"共 {len(self.batch_files)} 个 PDF" if has_files else "尚未添加 PDF")

    def remove_batch_files(self) -> None:
        rows = sorted((self.batch_list.row(item) for item in self.batch_list.selectedItems()), reverse=True)
        for row in rows:
            del self.batch_files[row]
        self.refresh_batch_list()

    def choose_batch_output_dir(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "选择批量输出文件夹", self.batch_output_dir.text())
        if folder:
            self.batch_output_dir.setText(folder)

    def start_batch_compression(self) -> None:
        if not self.batch_files or self.active_task:
            return
        files = tuple(self.batch_files)
        folder = Path(self.batch_output_dir.text())
        use_target = self.batch_target_checkbox.isChecked()
        target = round(self.batch_target_value.value() * (1024 * 1024 if self.batch_target_unit.currentText() == "MB" else 1024))
        def work(*, progress, cancelled):  # type: ignore[no-untyped-def]
            results, failures = [], []
            folder.mkdir(parents=True, exist_ok=True)
            for index, source in enumerate(files, start=1):
                if cancelled():
                    break
                stem = source.stem[:-14] if source.stem.endswith("_PDFStudioLite") else source.stem
                destination = folder / f"{stem}_PDFStudioLite.pdf"
                counter = 2
                while destination.exists():
                    destination = folder / f"{stem}_PDFStudioLite_{counter}.pdf"
                    counter += 1
                try:
                    if use_target:
                        result = compress_to_target(source, destination, target, lambda c, t, m: progress(round(((index - 1) + c / max(t, 1)) * 100), len(files) * 100, f"{source.name} · {m}"), cancelled)
                    else:
                        result = lossless_optimize(source, destination)
                    results.append(result)
                except Exception as error:
                    failures.append(f"{source.name}：{error}")
                progress(index, len(files), f"正在处理 {index} / {len(files)} 个文件")
            return {"results": results, "failures": failures, "folder": folder}
        self.active_task = FunctionTask(work)
        self.active_task.signals.progress.connect(self._task_progress)
        self.active_task.signals.result.connect(self._batch_complete)
        self.active_task.signals.error.connect(lambda error: self.show_error("批量压缩失败", error))
        self.active_task.signals.finished.connect(self._task_finished)
        self.batch_cancel_button.setVisible(True)
        self.pool.start(self.active_task)

    def _batch_complete(self, result: object) -> None:
        data = result  # type: ignore[assignment]
        results, failures = data["results"], data["failures"]
        original = sum(item.original_bytes for item in results)
        output = sum(item.output_bytes for item in results)
        QMessageBox.information(self, "批量压缩完成", f"成功：{len(results)}\n失败：{len(failures)}\n节省：{self.format_size(max(0, original-output))}\n输出：{data['folder']}")

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        files = [Path(url.toLocalFile()) for url in event.mimeData().urls() if url.isLocalFile()]
        if any(path.suffix.lower() in SUPPORTED_SUFFIXES for path in files):
            event.acceptProposedAction()
            self.statusBar().showMessage("松开鼠标即可导入本地图片或 PDF")
            return
        super().dragEnterEvent(event)

    def dropEvent(self, event: QDropEvent) -> None:
        files = [
            url.toLocalFile()
            for url in event.mimeData().urls()
            if url.isLocalFile() and Path(url.toLocalFile()).suffix.lower() in SUPPORTED_SUFFIXES
        ]
        if files:
            self.add_files(files, self.page_grid.count())
            event.acceptProposedAction()
            return
        super().dropEvent(event)

    def refresh_grid(self) -> None:
        self.page_grid.clear()
        self.source_list.clear()
        seen: set[Path] = set()
        placeholder = self._icon(QStyle.StandardPixmap.SP_FileIcon)
        for number, page_ref in enumerate(self.model.pages, start=1):
            if page_ref.uid not in self.known_page_uids:
                self.image_checked_uids.add(page_ref.uid)
            item = QListWidgetItem(placeholder, f"第 {number} 页")
            item.setData(Qt.ItemDataRole.UserRole, page_ref.uid)
            item.setData(Qt.ItemDataRole.UserRole + 1, page_ref)
            item.setTextAlignment(Qt.AlignmentFlag.AlignHCenter)
            item.setSizeHint(QSize(self.thumbnail_size + 28, self.thumbnail_size + 50))
            item.setToolTip(f"{page_ref.source.name}\n源页：{page_ref.source_page + 1}\n旋转：{page_ref.rotation}°")
            self.page_grid.addItem(item)
            self._load_thumbnail(item, page_ref)
            if page_ref.source not in seen:
                source_item = QListWidgetItem(page_ref.source.name)
                source_item.setData(Qt.ItemDataRole.UserRole, str(page_ref.source))
                source_item.setToolTip(f"{page_ref.source}\n选中后按 Delete，或点击 × 删除全部相关页面")
                self.source_list.addItem(source_item)
                seen.add(page_ref.source)
        self.page_grid.setIconSize(QSize(self.thumbnail_size, self.thumbnail_size))
        self.empty_state.setVisible(not self.model.pages)
        self.workspace_title.setText(f"页面  {len(self.model.pages)}")
        self.source_summary.setText(f"{len(seen)} 个文件 · {len(self.model.pages)} 页" if seen else "尚未添加文件")
        total_source_bytes = self.model.estimated_bytes
        self.current_source_bytes = total_source_bytes
        self.current_size.setText(self.format_size(total_source_bytes) if total_source_bytes else "—")
        self.current_size.setToolTip(
            f"按当前页面计划估算：{total_source_bytes:,} 字节。实际导出大小以生成结果为准。"
            if total_source_bytes
            else "尚未添加文件"
        )
        live_uids = {page.uid for page in self.model.pages}
        self.image_checked_uids.intersection_update(live_uids)
        self.known_page_uids = live_uids
        self._apply_image_checkboxes()
        self._update_actions()

    def _update_target_label(self, *_: object) -> None:
        if not hasattr(self, "target_size_label"):
            return
        multiplier = 1024 * 1024 if self.target_unit.currentText() == "MB" else 1024
        self.target_size_label.setText(self.format_size(round(self.target_value.value() * multiplier)))

    def _toggle_target_controls(self, checked: bool) -> None:
        self.target_controls.setVisible(checked)
        self.target_size_label.setVisible(checked)
        self.target_size_caption.setVisible(checked)

    def _load_thumbnail(self, item: QListWidgetItem, page_ref: PageRef) -> None:
        uid = page_ref.uid
        cached = self.thumbnail_cache.get(uid)
        if cached is not None:
            self._apply_thumbnail((uid, cached))
            return

        def work(*, progress, cancelled):  # type: ignore[no-untyped-def]
            return uid, render_thumbnail(page_ref, self.thumbnail_size * 2)

        task = FunctionTask(work)
        task.signals.result.connect(self._apply_thumbnail)
        self.pool.start(task)

    def _apply_thumbnail(self, result: object) -> None:
        uid, data = result  # type: ignore[misc]
        self.thumbnail_cache[uid] = data
        image = QImage.fromData(QByteArray(data), "PNG")
        if image.isNull():
            return
        target_row = next(
            (index for index in range(self.page_grid.count()) if self.page_grid.item(index).data(Qt.ItemDataRole.UserRole) == uid),
            -1,
        )
        if (
            target_row >= 0
            and self.workspace_mode == WorkspaceMode.WATERMARK
            and self.watermark_preview_asset is not None
            and target_row in self._watermark_preview_pages()
        ):
            image = draw_watermark_preview(image, self.watermark_preview_asset, self.watermark_panel.spec())
        pixmap = QPixmap.fromImage(image)
        canvas = QPixmap(self.thumbnail_size + 8, self.thumbnail_size + 8)
        canvas.fill(Qt.GlobalColor.transparent)
        scaled = pixmap.scaled(self.thumbnail_size, self.thumbnail_size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        from PySide6.QtGui import QPainter

        painter = QPainter(canvas)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect((canvas.width() - scaled.width()) // 2 + 3, (canvas.height() - scaled.height()) // 2 + 4, scaled.width(), scaled.height(), Qt.GlobalColor.lightGray)
        painter.drawPixmap((canvas.width() - scaled.width()) // 2, (canvas.height() - scaled.height()) // 2, scaled)
        painter.end()
        for index in range(self.page_grid.count()):
            item = self.page_grid.item(index)
            if item.data(Qt.ItemDataRole.UserRole) == uid:
                item.setIcon(QIcon(canvas))
                break

    def selected_rows(self) -> list[int]:
        return sorted(self.page_grid.row(item) for item in self.page_grid.selectedItems())

    def delete_selected(self) -> None:
        rows = self.selected_rows()
        if rows:
            self.model.delete(rows)
            self.refresh_grid()
            self.statusBar().showMessage(f"已删除 {len(rows)} 页 · 可撤销", 5000)

    def delete_source_file(self, source: Path) -> None:
        resolved = source.resolve()
        rows = [index for index, page in enumerate(self.model.pages) if page.source.resolve() == resolved]
        if not rows:
            return
        name = self.model.pages[rows[0]].source.name
        self.model.delete(rows)
        self.refresh_grid()
        self.statusBar().showMessage(f"已删除文件 {name} 的 {len(rows)} 页 · 可撤销", 5000)

    def duplicate_selected(self) -> None:
        self.model.duplicate(self.selected_rows())
        self.refresh_grid()

    def rotate_selected(self) -> None:
        self.rotate_selected_degrees(90)

    def rotate_selected_degrees(self, degrees: int) -> None:
        self.model.rotate(self.selected_rows(), degrees)
        self.refresh_grid()

    def rotate_all_pages(self, degrees: int) -> None:
        if not self.model.pages:
            return
        self.model.rotate(range(len(self.model.pages)), degrees)
        self.refresh_grid()
        self.statusBar().showMessage("已旋转全部页面 · 可撤销", 3500)

    def rotate_page(self, row: int) -> None:
        if 0 <= row < len(self.model.pages):
            self.model.rotate([row], 90)
            self.refresh_grid()

    def move_selected(self, direction: int) -> None:
        rows = self.selected_rows()
        if not rows:
            return
        selected_uids = {self.model.pages[row].uid for row in rows}
        self.model.move_relative(rows, direction)
        self.refresh_grid()
        for row in range(self.page_grid.count()):
            item = self.page_grid.item(row)
            if item.data(Qt.ItemDataRole.UserRole) in selected_uids:
                item.setSelected(True)
        self.statusBar().showMessage("页面顺序已更新 · 可撤销", 3500)

    def undo(self) -> None:
        if self.model.undo():
            self.refresh_grid()
            self.statusBar().showMessage("已撤销", 2500)

    def redo(self) -> None:
        if self.model.redo():
            self.refresh_grid()
            self.statusBar().showMessage("已重做", 2500)

    def reset_workspace(self) -> None:
        if not self.model.pages or self.active_task:
            return
        choice = QMessageBox.question(
            self,
            "确认重置工作区？",
            "将清空当前导入的全部页面和编辑历史。\n本地源文件不会被删除或修改。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if choice != QMessageBox.StandardButton.Yes:
            return
        self.model.reset()
        self.page_grid.clearSelection()
        self.actual_size.setText("—")
        self.ratio_label.setText("—")
        self.error_label.setText("—")
        self.progress.setValue(0)
        self.progress_text.setText("就绪")
        self.compress_checkbox.setChecked(False)
        self.gap_checkbox.setChecked(False)
        self.refresh_grid()
        self.statusBar().showMessage("工作区已重置 · 源文件未修改", 5000)

    def apply_grid_order(self, uids: list[str]) -> None:
        try:
            self.model.apply_order(uids)
            self.refresh_grid()
            self.statusBar().showMessage("页面顺序已更新 · 可撤销", 3500)
        except ValueError as error:
            self.show_error("无法调整页面顺序", str(error))

    def set_thumbnail_size(self, value: int) -> None:
        self.thumbnail_size = value
        self.page_grid.setIconSize(QSize(value, value))
        for index in range(self.page_grid.count()):
            self.page_grid.item(index).setSizeHint(QSize(value + 28, value + 50))

    def choose_output_dir(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "选择输出位置", self.output_dir.text())
        if folder:
            self.output_dir.setText(folder)

    def output_path(self) -> Path:
        filename = self.filename.text().strip()
        if not filename.lower().endswith(".pdf"):
            filename += ".pdf"
        return Path(self.output_dir.text().strip()) / filename

    def start_export(self) -> None:
        self._start_export(tuple(self.model.pages), self.output_path())

    def export_selected_pages(self) -> None:
        pages = tuple(self.model.pages[row] for row in self.selected_rows())
        if not pages or self.active_task:
            return
        suggested = self.output_path().with_name(f"{self.output_path().stem}-选中页面.pdf")
        filename, _ = QFileDialog.getSaveFileName(self, "导出选中页面", str(suggested), "PDF 文件 (*.pdf)")
        if filename:
            destination = Path(filename)
            if destination.suffix.lower() != ".pdf":
                destination = destination.with_suffix(".pdf")
            self._start_export(pages, destination)

    def _start_export(self, pages: tuple[PageRef, ...], destination: Path) -> None:
        if not pages or self.active_task:
            return
        if destination.exists():
            choice = QMessageBox.question(self, "替换现有文件？", f"{destination.name} 已存在。要替换它吗？")
            if choice != QMessageBox.StandardButton.Yes:
                return
        base_output = destination
        compress = self.compress_checkbox.isChecked()
        page_gap_mm = self.gap_value.value() if self.gap_checkbox.isChecked() else 0.0
        page_size_mm = PAGE_SIZES_MM[self.page_size_combo.currentText()] if self.uniform_size_checkbox.isChecked() else None
        orientation_map = {"自动适配": "auto", "纵向": "portrait", "横向": "landscape"}
        page_orientation = orientation_map[self.page_orientation_combo.currentText()]
        fill_page = self.page_fit_combo.currentIndex() == 1
        target = round(self.target_value.value() * (1024 * 1024 if self.target_unit.currentText() == "MB" else 1024))
        if compress and getattr(self, "current_source_bytes", 0) and target >= self.current_source_bytes:
            QMessageBox.warning(self, "目标大小无效", "压缩目标必须小于当前文件大小。")
            return

        def work(*, progress, cancelled):  # type: ignore[no-untyped-def]
            progress(0, 100, "正在生成页面…")
            if not compress:
                return export_pages(
                    pages,
                    base_output,
                    lambda c, t: progress(c, t, "正在生成页面…"),
                    cancelled,
                    page_gap_mm,
                    page_size_mm,
                    page_orientation,
                    fill_page,
                )
            intermediate = base_output.with_name(f".{base_output.stem}.source.pdf")
            try:
                export_pages(
                    pages,
                    intermediate,
                    lambda c, t: progress(c, max(t, 1) * 5, "正在生成页面…"),
                    cancelled,
                    page_gap_mm,
                    page_size_mm,
                    page_orientation,
                    fill_page,
                )
                return compress_to_target(
                    intermediate,
                    base_output,
                    target,
                    lambda c, t, message: progress(20 + round(c / max(t, 1) * 80), 100, message),
                    cancelled,
                )
            finally:
                intermediate.unlink(missing_ok=True)

        self.active_task = FunctionTask(work)
        self.active_task.signals.progress.connect(self._task_progress)
        self.active_task.signals.result.connect(self._export_complete)
        self.active_task.signals.error.connect(lambda error: self.show_error("导出失败", error))
        self.active_task.signals.finished.connect(self._task_finished)
        self.export_button.setEnabled(False)
        self.cancel_button.setVisible(True)
        self.progress.setValue(1)
        self.progress.setTextVisible(True)
        self.progress_text.setText("准备导出…")
        self.pool.start(self.active_task)

    def _task_progress(self, current: int, total: int, message: str) -> None:
        value = round(current / max(total, 1) * 100)
        self.progress.setValue(value)
        self.progress_text.setText(message or "处理中…")
        if hasattr(self, "image_progress"):
            self.image_progress.setValue(value)
            self.image_progress_text.setText(message or "处理中…")
        if hasattr(self, "batch_progress"):
            self.batch_progress.setValue(value)
            self.batch_status.setText(message or "处理中…")
        if hasattr(self, "watermark_panel") and self.workspace_mode == WorkspaceMode.WATERMARK:
            if self.watermark_panel.tabs.currentIndex() == 0:
                self.watermark_panel.status.setText(message or "处理中…")
            else:
                self.watermark_panel.remove_status.setText(message or "处理中…")

    def _export_complete(self, result: object) -> None:
        path: Path
        if isinstance(result, CompressionResult):
            path = result.output_path
            self.actual_size.setText(self.format_size(result.output_bytes))
            self.ratio_label.setText(f"{result.ratio:.1%}")
            if result.target_bytes:
                self.target_size_label.setText(self.format_size(result.target_bytes))
                error_bytes = abs(result.target_bytes - result.output_bytes)
                self.error_label.setText(f"{self.format_size(error_bytes)}（{result.target_error_ratio:.1%}）")
            self.progress_text.setText(result.message)
        else:
            path = Path(result)  # type: ignore[arg-type]
            self.actual_size.setText(self.format_size(path.stat().st_size))
            self.progress_text.setText("导出完成")
        self.progress.setValue(100)
        self.statusBar().showMessage(f"已导出：{path}", 10000)
        ExportResultDialog(path, result if isinstance(result, CompressionResult) else None, self).exec()

    def _task_finished(self) -> None:
        self.active_task = None
        self.export_button.setEnabled(bool(self.model.pages))
        self.cancel_button.setVisible(False)
        if hasattr(self, "image_cancel_button"):
            self.image_cancel_button.setVisible(False)
        if hasattr(self, "batch_cancel_button"):
            self.batch_cancel_button.setVisible(False)
            self.batch_start_button.setEnabled(bool(self.batch_files))
        if hasattr(self, "watermark_panel"):
            self.watermark_panel.set_busy(False)
        self.progress.setTextVisible(False)
        pending_scan = self.pending_watermark_scan
        if pending_scan is not None:
            current = Path(self.watermark_panel.remove_source.text().strip())
            if current.is_file() and current.resolve() == pending_scan:
                QTimer.singleShot(0, self.start_watermark_scan)
            else:
                self.pending_watermark_scan = None

    def cancel_task(self) -> None:
        if self.active_task:
            self.active_task.cancel()
            self.progress_text.setText("正在安全取消…")

    def show_preview(self, row: int) -> None:
        page_ref: PageRef = self.page_grid.item(row).data(Qt.ItemDataRole.UserRole + 1)
        try:
            data = render_thumbnail(page_ref, 1200)
            dialog = QDialog(self)
            dialog.setWindowTitle(f"第 {row + 1} 页 · {page_ref.source.name}")
            dialog.resize(800, 760)
            layout = QVBoxLayout(dialog)
            label = QLabel()
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            pixmap = QPixmap()
            pixmap.loadFromData(data)
            label.setPixmap(pixmap)
            layout.addWidget(label)
            dialog.exec()
        except Exception as error:
            self.show_error("无法预览页面", str(error))

    def _update_actions(self) -> None:
        has_pages = bool(self.model.pages)
        has_selection = bool(self.selected_rows()) if hasattr(self, "page_grid") else False
        self.delete_action.setEnabled(has_selection)
        self.duplicate_action.setEnabled(has_selection)
        self.rotate_action.setEnabled(has_selection)
        self.rotate_left_action.setEnabled(has_selection)
        rows = self.selected_rows() if has_selection else []
        can_left = bool(rows) and min(rows) > 0
        can_right = bool(rows) and max(rows) < len(self.model.pages) - 1
        self.move_left_action.setEnabled(can_left)
        self.move_right_action.setEnabled(can_right)
        if hasattr(self, "move_controls"):
            self.move_controls.setVisible(has_selection)
            self.move_left_button.setEnabled(can_left)
            self.move_right_button.setEnabled(can_right)
            self.selection_summary.setText(f"已选择 {len(rows)} 页" if has_selection else "")
        self.export_selected_action.setEnabled(has_selection and self.active_task is None)
        self.undo_action.setEnabled(self.model.can_undo)
        self.redo_action.setEnabled(self.model.can_redo)
        self.export_action.setEnabled(has_pages and self.active_task is None)
        self.reset_action.setEnabled(has_pages and self.active_task is None)
        if hasattr(self, "export_button"):
            self.export_button.setEnabled(has_pages and self.active_task is None)

    def show_page_context_menu(self, position: object) -> None:
        from PySide6.QtWidgets import QMenu

        menu = QMenu(self)
        menu.addAction(self.duplicate_action)
        menu.addAction(self.rotate_action)
        menu.addAction(self.rotate_left_action)
        menu.addAction(self.delete_action)
        menu.addSeparator()
        menu.addAction(self.export_selected_action)
        menu.exec(self.page_grid.viewport().mapToGlobal(position))  # type: ignore[arg-type]

    @staticmethod
    def format_size(size: int) -> str:
        if size >= 1024 * 1024:
            decimals = 3 if size < 100 * 1024 * 1024 else 2
            return f"{size / (1024 * 1024):.{decimals}f} MB"
        if size >= 1024:
            return f"{size / 1024:.1f} KB"
        return f"{size} B"

    def show_error(self, title: str, detail: str) -> None:
        self.progress_text.setText(title)
        QMessageBox.critical(self, title, detail.split("\n\n", 1)[0])

    def closeEvent(self, event: QCloseEvent) -> None:
        if self.active_task:
            choice = QMessageBox.question(self, "任务仍在运行", "要取消当前任务并退出吗？")
            if choice != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            self.active_task.cancel()
        event.accept()
