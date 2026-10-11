from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Tokens:
    canvas: str = "#E9E9E6"
    surface: str = "#F7F7F4"
    surface_alt: str = "#EFEFEC"
    text: str = "#292927"
    text_secondary: str = "#676762"
    accent: str = "#E66A1F"
    accent_hover: str = "#F0782A"
    accent_pressed: str = "#C95414"
    divider: str = "#CFCFC9"
    focus: str = "#F29A5F"
    destructive: str = "#B83A32"
    success: str = "#3B7D4A"
    radius: int = 7


TOKENS = Tokens()


def application_stylesheet(dark: bool = False) -> str:
    t = TOKENS
    base = f"""
    * {{
        font-family: "Segoe UI Variable", "Microsoft YaHei UI", "Segoe UI";
        font-size: 13px;
        color: {t.text};
    }}
    QMainWindow, QWidget#Root {{ background: {t.canvas}; }}
    QWidget#WatermarkPanel, QWidget#WatermarkScrollContent, QWidget#WatermarkViewport, QWidget#LabeledSwitch,
    QScrollArea#WatermarkScroll {{ background: transparent; border: none; }}
    QScrollArea#InspectorScroll, QWidget#PdfInspectorContent {{ background: transparent; border: none; }}
    QMenuBar {{ background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #FAFAF8, stop:1 #E8E8E4); border-bottom: 1px solid #BDBDB7; padding: 2px; }}
    QMenuBar::item {{ padding: 6px 10px; border-radius: 5px; }}
    QMenuBar::item:selected {{ background: #DEDEDA; }}
    QMenu {{ background: {t.surface}; border: 1px solid #B7B7B1; padding: 6px; }}
    QMenu::item {{ min-height: 26px; padding: 4px 28px 4px 10px; border-radius: 5px; }}
    QMenu::item:selected {{ background: #F6E1D3; color: #7D3210; }}
    QMessageBox {{ background: {t.surface}; }}
    QMessageBox QLabel {{ background: transparent; color: {t.text}; min-width: 0; }}
    QMessageBox QPushButton {{ min-width: 72px; }}
    QToolBar {{ background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #F8F8F5, stop:1 #E5E5E1); border: none; border-bottom: 1px solid #BFBFB9; spacing: 5px; padding: 7px 12px; }}
    QToolButton {{ background: transparent; border: 1px solid transparent; border-radius: 7px; min-width: 30px; min-height: 30px; padding: 3px 8px; }}
    QToolButton:hover {{ background: #DDDDD8; border-color: #C2C2BC; }}
    QToolButton:pressed {{ background: #CECEC8; border-color: #AFAFA9; padding-top: 4px; }}
    QToolButton:disabled {{ color: #B7B7BC; }}
    QToolButton:focus {{ border: 2px solid {t.focus}; }}
    QToolButton#PrimaryToolButton {{ background: {t.accent}; color: white; padding: 3px 14px; }}
    QToolButton#PrimaryToolButton:hover {{ background: {t.accent_hover}; }}
    QToolButton#PrimaryToolButton:pressed {{ background: {t.accent_pressed}; }}
    QSplitter::handle {{ background: #BFBFBA; width: 1px; }}
    QWidget#Sidebar, QWidget#Inspector {{ background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #F3F3F0, stop:1 #E9E9E5); }}
    QWidget#EmptyState {{ background: {t.canvas}; }}
    QWidget#PageStack {{ background: {t.canvas}; border: none; }}
    QLabel#BrandLogo {{ background: transparent; border: none; }}
    QLabel#PanelTitle {{ font-size: 15px; font-weight: 600; }}
    QLabel#SectionTitle {{ font-size: 11px; font-weight: 600; color: {t.text_secondary}; }}
    QLabel#Secondary {{ color: {t.text_secondary}; }}
    QLabel#EmptyTitle {{ font-size: 20px; font-weight: 600; }}
    QLabel#EmptyHint {{ color: {t.text_secondary}; font-size: 13px; }}
    QLabel#DialogTitle {{ font-size: 17px; font-weight: 600; }}
    QLabel#SuccessBadge {{ background: #E7F6EA; color: {t.success}; border-radius: 18px; font-size: 20px; font-weight: 700; }}
    QLabel#PathLabel {{ background: {t.surface_alt}; border: 1px solid {t.divider}; border-radius: 7px; padding: 8px; }}
    QListWidget#SourceList {{ background: transparent; border: none; outline: none; }}
    QListWidget#SourceList::item {{ border-radius: 7px; padding: 7px 8px; margin: 1px 4px; }}
    QListWidget#SourceList::item:selected {{ background: #F3D8C5; color: #74310E; border: 1px solid #D9A27F; }}
    QPushButton#SourceRemoveButton {{ background: #F6E0D1; color: #8A3511; border: 1px solid #D79B72; border-radius: 12px; min-width: 22px; min-height: 22px; max-width: 22px; max-height: 22px; padding: 0; font-size: 17px; font-weight: 600; }}
    QPushButton#SourceRemoveButton:hover {{ background: {t.accent}; color: white; border-color: {t.accent_pressed}; }}
    QListWidget#WatermarkDetectionList {{ background: #E4E4E0; color: {t.text}; border: 1px solid #B9B9B3; border-radius: 9px; outline: none; padding: 4px; }}
    QListWidget#WatermarkDetectionList::item {{ background: #F4F4F1; color: {t.text}; border: 1px solid #CECEC8; border-radius: 7px; padding: 8px; margin: 3px; }}
    QListWidget#WatermarkDetectionList::item:selected {{ background: #F6E0D1; color: #74310E; border-color: {t.accent}; }}
    QListWidget#WatermarkDetectionList::item:disabled {{ color: {t.text_secondary}; background: #E9E9E5; }}
    QListWidget#PageGrid {{ background: #E5E5E2; border: none; outline: none; padding: 18px; }}
    QListWidget#PageGrid::item {{ background: transparent; border: 2px solid transparent; border-radius: 8px; padding: 8px; margin: 6px; }}
    QListWidget#PageGrid::item:hover {{ background: rgba(255,255,255,90); }}
    QListWidget#PageGrid::item:selected {{ background: #F6E0D1; border: 2px solid {t.accent}; color: {t.text}; }}
    QLineEdit, QTextEdit, QSpinBox, QDoubleSpinBox, QComboBox {{ background: #E4E4E0; border: 1px solid #B9B9B3; border-top-color: #9F9F99; border-radius: 9px; min-height: 34px; padding: 3px 10px; selection-background-color: {t.accent}; }}
    QLineEdit:hover, QTextEdit:hover, QSpinBox:hover, QDoubleSpinBox:hover, QComboBox:hover {{ border-color: #92928D; }}
    QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{ border: 2px solid {t.focus}; }}
    QPushButton {{ background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #FFFFFF, stop:0.48 #F4F4F1, stop:1 #D8D8D3); border: 1px solid #AFAFA9; border-top-color: #D8D8D3; border-radius: 9px; min-height: 34px; padding: 3px 12px; }}
    QPushButton:hover {{ background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #FFFFFF, stop:1 #E5E5E0); border-color: #999994; }}
    QPushButton:pressed {{ background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #C8C8C3, stop:1 #E5E5E0); border-top-color: #8F8F8A; padding: 4px 12px 2px 12px; }}
    QPushButton:focus {{ border: 2px solid {t.focus}; }}
    QPushButton#PrimaryButton {{ background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #F58A43, stop:0.5 {t.accent}, stop:1 #C95113); border-color: #A84410; border-top-color: #F7A16A; color: white; font-weight: 600; }}
    QPushButton#PrimaryButton:hover {{ background: {t.accent_hover}; }}
    QPushButton#PrimaryButton:pressed {{ background: {t.accent_pressed}; }}
    QPushButton#PrimaryButton:disabled {{ background: #C8B3A5; border-color: #B4A59B; color: #EEE7E2; }}
    QPushButton#DestructiveButton {{ color: {t.destructive}; }}
    QPushButton#PageRotateButton {{ background: rgba(255,255,255,235); border: 1px solid {t.divider}; border-radius: 14px; padding: 0; font-size: 17px; }}
    QPushButton#PageRotateButton:hover {{ background: {t.accent}; color: white; border-color: {t.accent}; }}
    QTabBar#SegmentedTabBar {{ background: transparent; border: none; }}
    QTabWidget::pane {{ border: none; }}
    QProgressBar {{ background: #CDCDC8; border: 1px solid #B0B0AA; border-radius: 4px; height: 7px; text-align: center; }}
    QProgressBar::chunk {{ background: {t.accent}; border-radius: 3px; }}
    QStatusBar {{ background: {t.surface}; border-top: 1px solid {t.divider}; color: {t.text_secondary}; }}
    QSlider::groove:horizontal {{ height: 5px; background: #C4C4BF; border: 1px solid #A8A8A2; border-radius: 2px; }}
    QSlider::handle:horizontal {{ width: 18px; margin: -7px 0; background: qradialgradient(cx:0.35,cy:0.3,radius:0.8, stop:0 #FFFFFF, stop:0.65 #DADAD5, stop:1 #8E8E89); border: 1px solid #777772; border-radius: 9px; }}
    QSlider::sub-page:horizontal {{ background: {t.accent}; border-radius: 2px; }}
    """
    if not dark:
        return base
    return base + """
    * { color: #F2F2EF; }
    QMainWindow, QWidget#Root, QWidget#EmptyState { background: #1D1E20; }
    QWidget#WatermarkPanel, QWidget#WatermarkScrollContent, QWidget#WatermarkViewport, QWidget#LabeledSwitch,
    QScrollArea#WatermarkScroll { background: transparent; border: none; }
    QScrollArea#InspectorScroll, QWidget#PdfInspectorContent { background: transparent; border: none; }
    QMenuBar, QMenu, QToolBar, QStatusBar { background: #292A2C; border-color: #454649; }
    QMessageBox { background: #292A2C; }
    QMessageBox QLabel { background: transparent; color: #F2F2EF; }
    QMessageBox QPushButton { background: #3B3C3F; color: #F2F2EF; border-color: #606166; }
    QMessageBox QPushButton:hover { background: #48494D; border-color: #74757A; }
    QWidget#Sidebar, QWidget#Inspector { background: #27282A; }
    QListWidget#PageGrid { background: #1D1E20; }
    QListWidget#PageGrid::item:hover, QMenuBar::item:selected, QToolButton:hover { background: #343538; }
    QListWidget#PageGrid::item:selected { background: #4A2D20; border-color: #F07A32; color: #FFFFFF; }
    QListWidget#SourceList::item:selected { background: #4A2D20; color: #FFFFFF; border-color: #8D4C29; }
    QPushButton#SourceRemoveButton { background: #4A2D20; color: #FFB080; border-color: #8D4C29; }
    QPushButton#SourceRemoveButton:hover { background: #E66A1F; color: #FFFFFF; border-color: #F07A32; }
    QListWidget#WatermarkDetectionList { background: #252628; color: #F2F2EF; border-color: #505155; }
    QListWidget#WatermarkDetectionList::item { background: #303134; color: #F2F2EF; border-color: #505155; }
    QListWidget#WatermarkDetectionList::item:selected { background: #4A2D20; color: #FFFFFF; border-color: #F07A32; }
    QListWidget#WatermarkDetectionList::item:disabled { background: #292A2C; color: #B4B4AE; }
    QLabel#Secondary, QLabel#EmptyHint, QStatusBar { color: #B4B4AE; }
    QLineEdit, QTextEdit, QSpinBox, QDoubleSpinBox, QComboBox, QPushButton {
        background: #303134; border-color: #505155; color: #F2F2EF;
    }
    QPushButton:hover { background: #3B3C40; }
    QProgressBar { background: #3B3C3F; border-color: #505155; }
    QSplitter::handle { background: #444548; }
    """


def apply_theme(application: object, dark: bool) -> None:
    if application is not None and hasattr(application, "setStyleSheet"):
        application.setProperty("darkTheme", dark)  # type: ignore[attr-defined]
        application.setStyleSheet(application_stylesheet(dark))  # type: ignore[attr-defined]
        for widget in application.allWidgets():  # type: ignore[attr-defined]
            widget.update()
