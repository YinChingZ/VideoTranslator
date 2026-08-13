"""Application theme tokens and Qt stylesheet generation.

The application deliberately keeps typography native: Qt chooses the platform
UI font, which provides better CJK coverage and accessibility than a hard-coded
font family.  Colours are centralized here so widgets and generated icons share
the same light/dark vocabulary.
"""

from __future__ import annotations

import logging
from typing import Dict, Mapping, Optional

from PyQt5.QtGui import QColor, QPalette
from PyQt5.QtWidgets import QApplication, QWidget

LIGHT_THEME: Dict[str, str] = {
    "primary": "#2563EB",
    "primary_hover": "#1D4ED8",
    "primary_pressed": "#1E40AF",
    "primary_soft": "#DBEAFE",
    "secondary": "#0F766E",
    "background": "#F6F7FB",
    "surface": "#FFFFFF",
    "surface_alt": "#F1F5F9",
    "surface_hover": "#E8EEF7",
    "text": "#172033",
    "text_muted": "#566176",
    "text_on_primary": "#FFFFFF",
    "border": "#CBD5E1",
    "border_strong": "#94A3B8",
    "focus": "#0B63CE",
    "selection": "#D6E7FF",
    "selection_text": "#102A56",
    "disabled_surface": "#E2E8F0",
    "disabled_text": "#64748B",
    "accent": "#7C3AED",
    "warning": "#B45309",
    "error": "#B91C1C",
    "success": "#047857",
}

DARK_THEME: Dict[str, str] = {
    "primary": "#2563EB",
    "primary_hover": "#1D4ED8",
    "primary_pressed": "#1E40AF",
    "primary_soft": "#172E55",
    "secondary": "#2DD4BF",
    "background": "#0F172A",
    "surface": "#172033",
    "surface_alt": "#1E293B",
    "surface_hover": "#29364A",
    "text": "#F8FAFC",
    "text_muted": "#CBD5E1",
    "text_on_primary": "#FFFFFF",
    "border": "#475569",
    "border_strong": "#64748B",
    "focus": "#93C5FD",
    "selection": "#1E4E8C",
    "selection_text": "#FFFFFF",
    "disabled_surface": "#263449",
    "disabled_text": "#94A3B8",
    "accent": "#C4B5FD",
    "warning": "#FBBF24",
    "error": "#FCA5A5",
    "success": "#6EE7B7",
}


class StyleManager:
    """Apply a consistent, accessible light, dark, or system theme."""

    VALID_THEMES = frozenset({"light", "dark", "system"})

    def __init__(self) -> None:
        self.current_theme = "light"
        self.requested_theme = "light"

    def apply_theme(self, theme: str, widget: Optional[QWidget] = None) -> str:
        """Apply *theme* and return the resolved light/dark theme name."""

        normalized = str(theme).lower()
        if normalized not in self.VALID_THEMES:
            logging.warning("Unsupported theme %r; using system theme", theme)
            normalized = "system"

        self.requested_theme = normalized
        resolved = self._resolve_system_theme() if normalized == "system" else normalized
        self.current_theme = resolved
        colors = DARK_THEME if resolved == "dark" else LIGHT_THEME
        self._apply_stylesheet(self._generate_stylesheet(colors), widget)
        self._apply_palette(colors, widget)
        return resolved

    def apply_light_theme(self, widget: Optional[QWidget] = None) -> None:
        self.apply_theme("light", widget)

    def apply_dark_theme(self, widget: Optional[QWidget] = None) -> None:
        self.apply_theme("dark", widget)

    def apply_system_theme(self, widget: Optional[QWidget] = None) -> str:
        return self.apply_theme("system", widget)

    def toggle_theme(self, widget: Optional[QWidget] = None) -> None:
        self.apply_theme("light" if self.current_theme == "dark" else "dark", widget)

    @staticmethod
    def _resolve_system_theme() -> str:
        app = QApplication.instance()
        if app is None:
            return "light"
        return "dark" if app.palette().window().color().lightness() < 128 else "light"

    def _generate_stylesheet(self, colors: Mapping[str, str]) -> str:
        """Generate QSS from design tokens without overriding the system font."""

        c = colors
        return f"""
        QWidget {{
            background-color: {c['background']};
            color: {c['text']};
            selection-background-color: {c['selection']};
            selection-color: {c['selection_text']};
        }}
        QWidget:disabled {{ color: {c['disabled_text']}; }}
        QMainWindow, QDialog {{ background-color: {c['background']}; }}
        QToolTip {{
            background-color: {c['surface']};
            color: {c['text']};
            border: 1px solid {c['border_strong']};
            border-radius: 4px;
            padding: 5px 7px;
        }}

        QLabel {{ background-color: transparent; }}
        QLabel[heading="true"] {{
            color: {c['text']};
            font-size: 18pt;
            font-weight: 600;
        }}
        QLabel[muted="true"] {{ color: {c['text_muted']}; }}

        QPushButton {{
            background-color: {c['surface']};
            color: {c['text']};
            border: 1px solid {c['border']};
            border-radius: 6px;
            padding: 7px 14px;
            min-height: 20px;
            min-width: 68px;
        }}
        QPushButton:hover {{
            background-color: {c['surface_hover']};
            border-color: {c['border_strong']};
        }}
        QPushButton:pressed {{ background-color: {c['surface_alt']}; }}
        QPushButton:focus {{
            border: 2px solid {c['focus']};
            padding: 6px 13px;
        }}
        QPushButton:disabled {{
            background-color: {c['disabled_surface']};
            color: {c['disabled_text']};
            border-color: {c['border']};
        }}
        QPushButton[primary="true"] {{
            background-color: {c['primary']};
            color: {c['text_on_primary']};
            border-color: {c['primary']};
            font-weight: 600;
        }}
        QPushButton[primary="true"]:hover {{
            background-color: {c['primary_hover']};
            border-color: {c['primary_hover']};
        }}
        QPushButton[primary="true"]:pressed {{
            background-color: {c['primary_pressed']};
            border-color: {c['primary_pressed']};
        }}
        QPushButton[primary="true"]:focus {{ border-color: {c['focus']}; }}
        QPushButton[primary="true"]:disabled {{
            background-color: {c['disabled_surface']};
            color: {c['disabled_text']};
            border-color: {c['border']};
        }}
        QPushButton[secondary="true"] {{
            background-color: transparent;
            color: {c['focus']};
            border-color: {c['focus']};
        }}

        QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox,
        QDateEdit, QTimeEdit, QDateTimeEdit, QComboBox {{
            background-color: {c['surface']};
            color: {c['text']};
            border: 1px solid {c['border']};
            border-radius: 5px;
            padding: 6px 8px;
            min-height: 20px;
        }}
        QLineEdit:hover, QTextEdit:hover, QPlainTextEdit:hover,
        QSpinBox:hover, QDoubleSpinBox:hover, QComboBox:hover {{
            border-color: {c['border_strong']};
        }}
        QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus,
        QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{
            border: 2px solid {c['focus']};
            padding: 5px 7px;
        }}
        QLineEdit:disabled, QTextEdit:disabled, QPlainTextEdit:disabled,
        QSpinBox:disabled, QDoubleSpinBox:disabled, QComboBox:disabled {{
            background-color: {c['disabled_surface']};
            color: {c['disabled_text']};
        }}
        QComboBox::drop-down {{ border: 0; width: 24px; }}
        QComboBox QAbstractItemView {{
            background-color: {c['surface']};
            color: {c['text']};
            border: 1px solid {c['border_strong']};
            selection-background-color: {c['selection']};
            selection-color: {c['selection_text']};
            outline: 0;
        }}

        QListView, QListWidget, QTreeView, QTreeWidget, QTableView, QTableWidget {{
            background-color: {c['surface']};
            alternate-background-color: {c['surface_alt']};
            color: {c['text']};
            border: 1px solid {c['border']};
            border-radius: 5px;
            outline: 0;
        }}
        QListView::item, QListWidget::item, QTreeView::item, QTreeWidget::item {{
            padding: 5px;
        }}
        QListView::item:hover, QListWidget::item:hover,
        QTreeView::item:hover, QTreeWidget::item:hover {{
            background-color: {c['surface_hover']};
        }}
        QListView::item:selected, QListWidget::item:selected,
        QTreeView::item:selected, QTreeWidget::item:selected,
        QTableView::item:selected, QTableWidget::item:selected {{
            background-color: {c['selection']};
            color: {c['selection_text']};
        }}
        QListView:focus, QListWidget:focus, QTreeView:focus, QTreeWidget:focus,
        QTableView:focus, QTableWidget:focus {{ border: 2px solid {c['focus']}; }}
        QHeaderView::section {{
            background-color: {c['surface_alt']};
            color: {c['text']};
            border: 0;
            border-right: 1px solid {c['border']};
            border-bottom: 1px solid {c['border']};
            padding: 6px;
            font-weight: 600;
        }}

        QGroupBox {{
            border: 1px solid {c['border']};
            border-radius: 7px;
            margin-top: 12px;
            padding-top: 10px;
            font-weight: 600;
        }}
        QGroupBox::title {{
            subcontrol-origin: margin;
            left: 9px;
            padding: 0 4px;
            background-color: {c['background']};
        }}
        QCheckBox, QRadioButton {{ spacing: 7px; background-color: transparent; }}
        QCheckBox:focus, QRadioButton:focus {{ color: {c['focus']}; }}

        QProgressBar {{
            background-color: {c['surface_alt']};
            color: {c['text']};
            border: 1px solid {c['border']};
            border-radius: 5px;
            min-height: 12px;
            text-align: center;
        }}
        QProgressBar::chunk {{
            background-color: {c['primary']};
            border-radius: 4px;
        }}
        QSlider::groove:horizontal {{
            background-color: {c['surface_alt']};
            height: 5px;
            border-radius: 2px;
        }}
        QSlider::handle:horizontal {{
            background-color: {c['primary']};
            border: 2px solid {c['surface']};
            width: 16px;
            height: 16px;
            margin: -7px 0;
            border-radius: 9px;
        }}
        QSlider::handle:horizontal:focus {{ border-color: {c['focus']}; }}

        QMenuBar {{
            background-color: {c['surface']};
            color: {c['text']};
            border-bottom: 1px solid {c['border']};
        }}
        QMenuBar::item {{ padding: 5px 8px; background: transparent; }}
        QMenuBar::item:selected, QMenuBar::item:pressed {{
            background-color: {c['surface_hover']};
        }}
        QMenu {{
            background-color: {c['surface']};
            color: {c['text']};
            border: 1px solid {c['border_strong']};
            padding: 4px;
        }}
        QMenu::item {{ padding: 6px 28px 6px 10px; border-radius: 4px; }}
        QMenu::item:selected {{
            background-color: {c['selection']};
            color: {c['selection_text']};
        }}
        QMenu::item:disabled {{ color: {c['disabled_text']}; }}
        QToolBar {{
            background-color: {c['surface']};
            border: 0;
            border-bottom: 1px solid {c['border']};
            spacing: 4px;
            padding: 4px;
        }}
        QToolButton {{
            background-color: transparent;
            border: 1px solid transparent;
            border-radius: 5px;
            padding: 5px;
        }}
        QToolButton:hover {{ background-color: {c['surface_hover']}; }}
        QToolButton:focus {{ border-color: {c['focus']}; }}
        QStatusBar {{
            background-color: {c['surface']};
            color: {c['text_muted']};
            border-top: 1px solid {c['border']};
        }}

        QTabWidget::pane {{
            background-color: {c['surface']};
            border: 1px solid {c['border']};
            border-radius: 6px;
        }}
        QTabBar::tab {{
            background-color: transparent;
            color: {c['text_muted']};
            border: 0;
            border-bottom: 2px solid transparent;
            padding: 8px 12px;
        }}
        QTabBar::tab:hover {{ color: {c['text']}; }}
        QTabBar::tab:selected {{
            color: {c['focus']};
            border-bottom-color: {c['focus']};
            font-weight: 600;
        }}
        QTabBar::tab:focus {{ border-bottom-color: {c['focus']}; }}

        QScrollBar:vertical {{
            background: transparent;
            width: 11px;
            margin: 1px;
        }}
        QScrollBar:horizontal {{
            background: transparent;
            height: 11px;
            margin: 1px;
        }}
        QScrollBar::handle:vertical, QScrollBar::handle:horizontal {{
            background-color: {c['border_strong']};
            border-radius: 4px;
            min-height: 24px;
            min-width: 24px;
        }}
        QScrollBar::handle:vertical:hover, QScrollBar::handle:horizontal:hover {{
            background-color: {c['text_muted']};
        }}
        QScrollBar::add-line, QScrollBar::sub-line,
        QScrollBar::add-page, QScrollBar::sub-page {{
            background: transparent;
            border: 0;
        }}

        #videoImportWidget {{ background-color: {c['background']}; }}
        #videoInfoFrame {{
            background-color: {c['surface']};
            border: 1px solid {c['border']};
            border-radius: 8px;
        }}
        #thumbnailPreview {{
            background-color: #111827;
            color: #F8FAFC;
            border: 1px solid {c['border']};
            border-radius: 6px;
        }}
        #dropZone {{
            background-color: {c['surface']};
            color: {c['text_muted']};
            border: 2px dashed {c['border_strong']};
            border-radius: 10px;
            padding: 20px;
        }}
        #dropZone:hover {{
            background-color: {c['primary_soft']};
            color: {c['text']};
            border-color: {c['primary']};
        }}
        #dropZone:focus {{
            background-color: {c['primary_soft']};
            color: {c['text']};
            border: 3px solid {c['focus']};
            padding: 19px;
        }}
        #dropZone[dragActive="true"] {{
            background-color: {c['primary_soft']};
            color: {c['text']};
            border: 3px solid {c['primary']};
            padding: 19px;
        }}
        .ProcessingWidget QLabel[stage="complete"] {{ color: {c['success']}; }}
        .ProcessingWidget QLabel[stage="error"] {{ color: {c['error']}; }}
        .ProcessingWidget QLabel[stage="waiting"] {{ color: {c['text_muted']}; }}
        #timelineWidget {{
            background-color: {c['surface_alt']};
            border: 1px solid {c['border']};
        }}
        #bilingualEditor {{ background-color: {c['surface']}; }}
        """

    @staticmethod
    def _apply_stylesheet(stylesheet: str, widget: Optional[QWidget] = None) -> None:
        target = widget or QApplication.instance()
        if target is None:
            logging.warning("Cannot apply stylesheet before QApplication is created")
            return
        target.setStyleSheet(stylesheet)

    @classmethod
    def _apply_palette(
        cls,
        colors: Mapping[str, str],
        widget: Optional[QWidget] = None,
    ) -> None:
        palette = cls._build_palette(colors)
        target = widget or QApplication.instance()
        if target is not None:
            target.setPalette(palette)

    @staticmethod
    def _build_palette(colors: Mapping[str, str]) -> QPalette:
        palette = QPalette()
        roles = {
            QPalette.Window: colors["background"],
            QPalette.WindowText: colors["text"],
            QPalette.Base: colors["surface"],
            QPalette.AlternateBase: colors["surface_alt"],
            QPalette.ToolTipBase: colors["surface"],
            QPalette.ToolTipText: colors["text"],
            QPalette.Text: colors["text"],
            QPalette.Button: colors["surface"],
            QPalette.ButtonText: colors["text"],
            QPalette.BrightText: colors["text_on_primary"],
            QPalette.Highlight: colors["primary"],
            QPalette.HighlightedText: colors["text_on_primary"],
            QPalette.Link: colors["focus"],
        }
        for role, value in roles.items():
            palette.setColor(role, QColor(value))
        for role in (QPalette.WindowText, QPalette.Text, QPalette.ButtonText):
            palette.setColor(QPalette.Disabled, role, QColor(colors["disabled_text"]))
        palette.setColor(QPalette.Disabled, QPalette.Button, QColor(colors["disabled_surface"]))
        palette.setColor(QPalette.Disabled, QPalette.Base, QColor(colors["disabled_surface"]))
        return palette

    def _set_application_palette(self, light: bool = True) -> None:
        """Compatibility wrapper retained for existing callers."""

        self._apply_palette(LIGHT_THEME if light else DARK_THEME)

    @staticmethod
    def _is_dark_color(hex_color: str) -> bool:
        color = QColor(hex_color)
        if not color.isValid():
            raise ValueError(f"Invalid color: {hex_color!r}")
        return color.lightness() < 128

    @staticmethod
    def _adjust_brightness(hex_color: str, amount: int) -> str:
        color = QColor(hex_color)
        if not color.isValid():
            raise ValueError(f"Invalid color: {hex_color!r}")
        return "#{:02x}{:02x}{:02x}".format(
            max(0, min(255, color.red() + amount)),
            max(0, min(255, color.green() + amount)),
            max(0, min(255, color.blue() + amount)),
        )

    @staticmethod
    def load_font(font_name: str, font_path: str) -> bool:
        """Load an optional application font without making it a dependency."""

        from PyQt5.QtGui import QFontDatabase

        try:
            font_id = QFontDatabase.addApplicationFont(font_path)
        except Exception:
            logging.exception("Failed to load font %s from %s", font_name, font_path)
            return False
        if font_id == -1:
            logging.error("Failed to load font %s from %s", font_name, font_path)
            return False
        return True

    def get_theme_colors(self) -> Dict[str, str]:
        return (DARK_THEME if self.current_theme == "dark" else LIGHT_THEME).copy()

    def get_specific_color(self, color_name: str) -> str:
        colors = self.get_theme_colors()
        return colors.get(color_name, "#FFFFFF" if self.current_theme == "dark" else "#000000")

    def get_adjusted_color_scheme(self, brightness_offset: int = 0) -> Dict[str, str]:
        return {
            name: self._adjust_brightness(color, brightness_offset)
            for name, color in self.get_theme_colors().items()
        }

    def get_custom_theme(self, primary_color: str) -> Dict[str, str]:
        if not QColor(primary_color).isValid():
            raise ValueError(f"Invalid primary color: {primary_color!r}")
        custom_theme = self.get_theme_colors()
        custom_theme["primary"] = QColor(primary_color).name()
        custom_theme["primary_hover"] = self._adjust_brightness(primary_color, -18)
        custom_theme["primary_pressed"] = self._adjust_brightness(primary_color, -34)
        return custom_theme
