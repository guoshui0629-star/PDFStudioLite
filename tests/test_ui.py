from __future__ import annotations

from pathlib import Path

from PIL import Image
import pymupdf
from PySide6.QtCore import QPoint, QPointF, QStandardPaths, Qt
from PySide6.QtGui import QKeyEvent, QWheelEvent
from PySide6.QtWidgets import QApplication, QLabel, QMessageBox, QScrollArea, QToolBar

from app.main import create_application
from app import __display_version__, __product_title__, __version__
from app.ui.main_window import MainWindow
from app.ui.theme import application_stylesheet
from app.ui.theme import apply_theme
from app.ui.components.skeuomorphic_switch import LabeledSwitch, SkeuomorphicSwitch
from app.ui.components.tactile_slider import TactileSlider
from app.core.workspace import WorkspaceMode
from app.resources import ui_resource_path


def test_main_window_starts_and_has_three_panes(tmp_path, monkeypatch) -> None:
    app = create_application([])
    window = MainWindow()
    window.show()
    app.processEvents()
    assert window.windowTitle() == "PDF Studio Lite V3.2"
    assert window.windowTitle() == __product_title__
    assert __display_version__ == "V3.2"
    assert __version__ == "3.2.0"
    assert not window.windowIcon().isNull()
    assert ui_resource_path("assets/branding/pdf-toaster-app.ico").is_file()
    assert ui_resource_path("assets/branding/pdf-toaster-app-512.png").is_file()
    assert window.splitter.count() == 3
    assert window.mode_selector.count() == 4
    assert window.workspace_mode == WorkspaceMode.PDF
    toolbar_actions = [action for toolbar in window.findChildren(QToolBar) for action in toolbar.actions()]
    assert window.export_action not in toolbar_actions
    expected_desktop = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DesktopLocation)
    assert window.output_dir.text() == expected_desktop
    assert window.empty_state.isVisibleTo(window)
    assert window.empty_state.geometry() == window.page_stack.rect()
    assert window.zoom_slider.width() >= 160
    assert window.zoom_slider.height() >= 34
    assert isinstance(window.zoom_slider, TactileSlider)
    assert window.zoom_slider.handle_diameter >= 22
    assert not hasattr(window, "mode_tabs")
    assert not window.compress_checkbox.isChecked()
    assert not window.target_controls.isVisibleTo(window)
    assert window.page_grid.dragDropOverwriteMode() is False
    assert not window.move_controls.isVisibleTo(window)
    assert isinstance(window.pdf_inspector_scroll, QScrollArea)
    assert window.pdf_inspector_scroll.widgetResizable()
    window.compress_checkbox.setChecked(True)
    window.batch_rotate_checkbox.setChecked(True)
    window.uniform_size_checkbox.setChecked(True)
    window.gap_checkbox.setChecked(True)
    app.processEvents()
    assert window.target_controls.isVisibleTo(window)
    assert window.pdf_inspector_scroll.verticalScrollBar().maximum() >= 0
    window.mode_selector.setCurrentIndex(1)
    app.processEvents()
    assert window.workspace_mode == WorkspaceMode.IMAGES
    assert window.inspector_title.text() == "导出为图片"
    assert window.image_format.count() == 4
    assert window.image_dpi.currentText() == "200 DPI"
    assert window.image_dpi.itemText(0) == "原图"
    window.mode_selector.setCurrentIndex(2)
    app.processEvents()
    assert window.workspace_mode == WorkspaceMode.BATCH
    assert window.workspace_stack.currentIndex() == 1
    assert not window.batch_start_button.isEnabled()
    assert window.batch_empty_state.findChild(QLabel, "BrandLogo") is not None
    batch_pdf = tmp_path / "批量.pdf"
    doc = pymupdf.open()
    doc.new_page()
    doc.save(batch_pdf)
    doc.close()
    page_count_before = len(window.model.pages)
    window.add_batch_files([str(batch_pdf)])
    assert window.batch_list.count() == 1
    assert window.batch_start_button.isEnabled()
    assert len(window.model.pages) == page_count_before
    window.mode_selector.setCurrentIndex(3)
    app.processEvents()
    assert window.workspace_mode == WorkspaceMode.WATERMARK
    assert window.inspector_title.text() == "水印管理"
    assert window.watermark_panel.font.isEditable()
    assert window.watermark_panel.opacity.value() == 25
    assert isinstance(window.watermark_panel.opacity, TactileSlider)
    assert window.watermark_panel.opacity.minimumHeight() >= 34
    assert window.watermark_panel.angle.value() == -45
    assert isinstance(window.watermark_panel.bold, SkeuomorphicSwitch)
    assert isinstance(window.watermark_panel.italic, SkeuomorphicSwitch)
    assert isinstance(window.compress_checkbox, LabeledSwitch)
    assert not window.add_action.icon().isNull()
    assert not window.delete_action.icon().isNull()
    assert window.watermark_panel.objectName() == "WatermarkPanel"
    assert window.watermark_panel.tabs.minimumHeight() >= 42
    segment_pixmap = window.mode_selector.grab()
    assert not segment_pixmap.isNull()
    segment_image = segment_pixmap.toImage()
    assert segment_image.pixelColor(0, 0).lightness() > 40
    assert segment_image.pixelColor(segment_image.width() - 1, 0).lightness() > 40
    assert not window.watermark_panel.tabs.grab().isNull()
    viewport = window.watermark_panel.stack.currentWidget().viewport()
    opacity_right = window.watermark_panel.opacity.mapTo(viewport, window.watermark_panel.opacity.rect().topRight()).x()
    assert opacity_right <= viewport.width()
    assert window.watermark_panel.position_group.checkedButton().property("positionValue") == "center"
    window.mode_selector.setCurrentIndex(0)
    image = tmp_path / "reset.png"
    Image.new("RGB", (20, 20), "navy").save(image)
    window.add_files([str(image)], 0)
    assert len(window.model.pages) == 1
    window.page_grid.item(0).setSelected(True)
    app.processEvents()
    assert window.move_controls.isVisibleTo(window)
    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.StandardButton.Yes)
    window.reset_workspace()
    assert window.model.pages == []
    assert not window.model.can_undo
    assert window.pool.waitForDone(5000)
    window.close()
    app.quit()


def test_dark_theme_has_semantic_dark_surfaces() -> None:
    stylesheet = application_stylesheet(True)
    assert "#1D1E20" in stylesheet
    assert "#F07A32" in stylesheet
    assert 'font-family: "Segoe UI Variable"' in stylesheet


def test_confirmation_dialog_has_explicit_light_and_dark_contrast() -> None:
    light = application_stylesheet(False)
    dark = application_stylesheet(True)
    assert "QMessageBox { background: #F7F7F4; }" in light
    assert "QMessageBox QLabel { background: transparent; color: #292927;" in light
    assert "QMessageBox { background: #292A2C; }" in dark
    assert "QMessageBox QLabel { background: transparent; color: #F2F2EF;" in dark


def test_segmented_tabs_repaint_for_dark_theme_without_light_patch() -> None:
    app = create_application([])
    window = MainWindow()
    window.show()
    apply_theme(app, True)
    app.processEvents()
    image = window.mode_selector.grab().toImage()
    corner = image.pixelColor(0, 0)
    center = image.pixelColor(image.width() // 2, image.height() // 2)
    assert corner.lightness() < 75
    assert center.lightness() < 125
    assert corner != center
    apply_theme(app, False)
    window.close()


def test_light_theme_explicitly_styles_watermark_surfaces_and_tall_controls() -> None:
    stylesheet = application_stylesheet(False)
    assert "QWidget#WatermarkScrollContent" in stylesheet
    assert "QWidget#WatermarkViewport" in stylesheet
    assert "min-height: 34px" in stylesheet
    assert "border-radius: 9px" in stylesheet


def test_pdf_drop_in_watermark_remove_mode_starts_scan(tmp_path, monkeypatch) -> None:
    app = create_application([])
    window = MainWindow()
    source = tmp_path / "待检测水印.pdf"
    doc = pymupdf.open()
    doc.new_page()
    doc.save(source)
    doc.close()
    scans: list[bool] = []
    monkeypatch.setattr(window, "start_watermark_scan", lambda: scans.append(True))
    window.mode_selector.setCurrentIndex(3)
    window.watermark_panel.tabs.setCurrentIndex(1)
    window.add_files([str(source)], 0)
    app.processEvents()
    assert Path(window.watermark_panel.remove_source.text()) == source.resolve()
    assert window.watermark_panel.remove_output.text().endswith("待检测水印_无水印_PDFStudioLite.pdf")
    assert scans == [True]
    assert "自动开始扫描" in window.watermark_panel.remove_status.text()
    window.close()


def test_watermark_scan_is_queued_while_another_task_is_active(tmp_path, monkeypatch) -> None:
    app = create_application([])
    window = MainWindow()
    source = tmp_path / "排队扫描.pdf"
    doc = pymupdf.open()
    doc.new_page()
    doc.save(source)
    doc.close()
    window.watermark_panel.set_remove_source(source, automatic=True)
    window.active_task = object()  # type: ignore[assignment]
    window.start_watermark_scan()
    assert window.pending_watermark_scan == source.resolve()
    assert "自动扫描" in window.watermark_panel.remove_status.text()
    queued: list[bool] = []
    monkeypatch.setattr(window, "start_watermark_scan", lambda: queued.append(True))
    window._task_finished()
    app.processEvents()
    assert queued == [True]
    window.close()


def test_stale_watermark_scan_result_does_not_replace_current_file(tmp_path) -> None:
    app = create_application([])
    window = MainWindow()
    old_source = tmp_path / "旧文件.pdf"
    current_source = tmp_path / "当前文件.pdf"
    for source in (old_source, current_source):
        doc = pymupdf.open()
        doc.new_page()
        doc.save(source)
        doc.close()
    window.watermark_panel.set_remove_source(current_source)
    window._watermark_scan_complete({"source": old_source.resolve(), "records": []})
    assert window.watermark_panel.remove_status.text() == "文件已选择，点击“扫描水印对象”。"
    window.close()


def test_mouse_wheel_never_changes_option_controls() -> None:
    app = create_application([])
    window = MainWindow()
    window.compress_checkbox.setChecked(True)
    window.uniform_size_checkbox.setChecked(True)
    window.show()
    app.processEvents()
    controls = (window.target_value, window.target_unit, window.page_size_combo, window.zoom_slider)
    values = [control.value() if hasattr(control, "value") else control.currentIndex() for control in controls]
    for control in controls:
        event = QWheelEvent(
            QPointF(control.rect().center()),
            QPointF(control.mapToGlobal(control.rect().center())),
            QPoint(),
            QPoint(0, 120),
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
            Qt.ScrollPhase.ScrollUpdate,
            False,
        )
        QApplication.sendEvent(control, event)
    actual = [control.value() if hasattr(control, "value") else control.currentIndex() for control in controls]
    assert actual == values
    window.close()


def test_source_file_can_be_deleted_with_delete_key_and_undone(tmp_path) -> None:
    app = create_application([])
    window = MainWindow()
    first = tmp_path / "一.pdf"
    second = tmp_path / "二.pdf"
    for path, pages in ((first, 2), (second, 1)):
        doc = pymupdf.open()
        for _ in range(pages):
            doc.new_page()
        doc.save(path)
        doc.close()
    window.add_files([str(first), str(second)], 0)
    assert window.source_list.count() == 2
    window.source_list.setCurrentRow(0)
    assert window.source_list.remove_button.text() == ""
    assert window.source_list.remove_button.accessibleName() == "删除此文件"
    QApplication.sendEvent(
        window.source_list,
        QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Delete, Qt.KeyboardModifier.NoModifier),
    )
    assert len(window.model.pages) == 1
    assert window.source_list.count() == 1
    assert window.model.can_undo
    window.undo()
    assert len(window.model.pages) == 3
    assert window.source_list.count() == 2
    window.close()
