"""Theme-aware application icons with deterministic vector fallbacks."""

from __future__ import annotations

import logging
import math
from pathlib import Path
from typing import Dict, Optional, Tuple

from PyQt5.QtCore import QPointF, QRectF, QSize, Qt
from PyQt5.QtGui import (
    QColor,
    QIcon,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QPolygonF,
)
from PyQt5.QtSvg import QSvgRenderer
from PyQt5.QtWidgets import QApplication

_ICON_SIZES = (16, 20, 24, 32, 48, 64)
_KNOWN_ICONS = frozenset(
    {
        "export",
        "folder",
        "next",
        "open",
        "pause",
        "play",
        "previous",
        "redo",
        "save",
        "settings",
        "stop",
        "undo",
    }
)


class IconManager:
    """Load packaged icons and provide crisp QPainter fallbacks.

    Missing assets never become random letter tiles. Known actions are rendered
    as familiar line icons; unknown names receive a neutral document glyph.
    """

    def __init__(self, icon_dir: str) -> None:
        self.icon_dir = Path(icon_dir)
        self.icon_cache: Dict[Tuple[str, str], QIcon] = {}
        self.current_theme = "light"

    def get_icon(self, name: str) -> QIcon:
        normalized = str(name).strip().lower() or "document"
        cache_key = (self.current_theme, normalized)
        if cache_key not in self.icon_cache:
            icon = self._load_icon_from_file(normalized)
            self.icon_cache[cache_key] = icon or self._generate_fallback_icon(normalized)
        return self.icon_cache[cache_key]

    def set_theme(self, theme: str) -> None:
        normalized = str(theme).lower()
        if normalized == "system":
            normalized = self._system_theme()
        if normalized not in {"light", "dark"}:
            logging.warning("Unsupported icon theme %r; using system theme", theme)
            normalized = self._system_theme()
        if normalized != self.current_theme:
            self.current_theme = normalized
            self.icon_cache.clear()

    @staticmethod
    def _system_theme() -> str:
        app = QApplication.instance()
        if app is None:
            return "light"
        return "dark" if app.palette().window().color().lightness() < 128 else "light"

    def _load_icon_from_file(self, name: str) -> Optional[QIcon]:
        """Load a theme-specific asset first, then a theme-neutral asset."""

        candidates = (
            self.icon_dir / self.current_theme / f"{name}.svg",
            self.icon_dir / f"{name}_{self.current_theme}.svg",
            self.icon_dir / f"{name}.svg",
            self.icon_dir / self.current_theme / f"{name}.png",
            self.icon_dir / f"{name}_{self.current_theme}.png",
            self.icon_dir / f"{name}.png",
        )
        for path in candidates:
            if not path.is_file():
                continue
            if path.suffix.lower() == ".svg":
                icon = self._load_svg_icon(path)
            else:
                icon = QIcon(str(path))
            if not icon.isNull():
                return icon
            logging.warning("Ignoring unreadable icon asset: %s", path)
        return None

    @staticmethod
    def _load_svg_icon(file_path: Path) -> QIcon:
        renderer = QSvgRenderer(str(file_path))
        if not renderer.isValid():
            return QIcon()
        icon = QIcon()
        for size in _ICON_SIZES:
            pixmap = QPixmap(size, size)
            pixmap.fill(Qt.transparent)
            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.Antialiasing)
            renderer.render(painter)
            painter.end()
            icon.addPixmap(pixmap)
        return icon

    def _generate_fallback_icon(self, name: str) -> QIcon:
        icon = QIcon()
        foreground = QColor("#334155" if self.current_theme == "light" else "#E2E8F0")
        disabled = QColor("#94A3B8" if self.current_theme == "light" else "#64748B")
        for size in _ICON_SIZES:
            icon.addPixmap(self._draw_icon(name, size, foreground), QIcon.Normal, QIcon.Off)
            icon.addPixmap(self._draw_icon(name, size, disabled), QIcon.Disabled, QIcon.Off)
        return icon

    @classmethod
    def _draw_icon(cls, name: str, size: int, color: QColor) -> QPixmap:
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing)

        scale = size / 24.0
        pen = QPen(color, max(1.4, 1.8 * scale), Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.scale(scale, scale)

        draw_name = name if name in _KNOWN_ICONS else "document"
        getattr(cls, f"_paint_{draw_name}")(painter, color)
        painter.end()
        return pixmap

    @staticmethod
    def _paint_open(painter: QPainter, color: QColor) -> None:
        IconManager._paint_folder(painter, color)

    @staticmethod
    def _paint_folder(painter: QPainter, color: QColor) -> None:
        path = QPainterPath()
        path.moveTo(3, 7)
        path.lineTo(3, 18.5)
        path.quadTo(3, 20, 4.5, 20)
        path.lineTo(19.5, 20)
        path.quadTo(21, 20, 21, 18.5)
        path.lineTo(21, 8.5)
        path.quadTo(21, 7, 19.5, 7)
        path.lineTo(12, 7)
        path.lineTo(9.5, 4.5)
        path.lineTo(4.5, 4.5)
        path.quadTo(3, 4.5, 3, 6)
        path.closeSubpath()
        painter.drawPath(path)
        painter.drawLine(QPointF(3.5, 10), QPointF(20.5, 10))

    @staticmethod
    def _paint_save(painter: QPainter, color: QColor) -> None:
        path = QPainterPath()
        path.moveTo(4, 3.5)
        path.lineTo(17.5, 3.5)
        path.lineTo(20.5, 6.5)
        path.lineTo(20.5, 20.5)
        path.lineTo(3.5, 20.5)
        path.lineTo(3.5, 3.5)
        path.closeSubpath()
        painter.drawPath(path)
        painter.drawRect(QRectF(7, 3.5, 9, 6))
        painter.drawRect(QRectF(7, 14, 10, 6.5))

    @staticmethod
    def _paint_export(painter: QPainter, color: QColor) -> None:
        painter.drawLine(QPointF(12, 15), QPointF(12, 3.5))
        painter.drawLine(QPointF(12, 3.5), QPointF(7.5, 8))
        painter.drawLine(QPointF(12, 3.5), QPointF(16.5, 8))
        path = QPainterPath()
        path.moveTo(5, 12)
        path.lineTo(4, 12)
        path.lineTo(4, 20)
        path.lineTo(20, 20)
        path.lineTo(20, 12)
        path.lineTo(19, 12)
        painter.drawPath(path)

    @staticmethod
    def _paint_settings(painter: QPainter, color: QColor) -> None:
        painter.drawEllipse(QPointF(12, 12), 4, 4)
        painter.drawEllipse(QPointF(12, 12), 7.5, 7.5)
        for angle in range(0, 360, 45):
            radians = math.radians(angle)
            inner = QPointF(12 + 7.5 * math.cos(radians), 12 + 7.5 * math.sin(radians))
            outer = QPointF(12 + 10 * math.cos(radians), 12 + 10 * math.sin(radians))
            painter.drawLine(inner, outer)

    @staticmethod
    def _paint_undo(painter: QPainter, color: QColor) -> None:
        path = QPainterPath(QPointF(6, 9))
        path.cubicTo(9, 5, 15.5, 5, 19, 9)
        path.cubicTo(21, 11.5, 20.5, 16, 17, 18.5)
        painter.drawPath(path)
        painter.drawLine(QPointF(6, 9), QPointF(6, 4.5))
        painter.drawLine(QPointF(6, 9), QPointF(10.5, 9))

    @staticmethod
    def _paint_redo(painter: QPainter, color: QColor) -> None:
        painter.save()
        painter.translate(24, 0)
        painter.scale(-1, 1)
        IconManager._paint_undo(painter, color)
        painter.restore()

    @staticmethod
    def _paint_next(painter: QPainter, color: QColor) -> None:
        painter.drawLine(QPointF(7, 4), QPointF(15, 12))
        painter.drawLine(QPointF(15, 12), QPointF(7, 20))
        painter.drawLine(QPointF(17.5, 4), QPointF(17.5, 20))

    @staticmethod
    def _paint_previous(painter: QPainter, color: QColor) -> None:
        painter.save()
        painter.translate(24, 0)
        painter.scale(-1, 1)
        IconManager._paint_next(painter, color)
        painter.restore()

    @staticmethod
    def _paint_play(painter: QPainter, color: QColor) -> None:
        painter.setBrush(color)
        painter.setPen(Qt.NoPen)
        painter.drawPolygon(QPolygonF([QPointF(7, 4), QPointF(20, 12), QPointF(7, 20)]))

    @staticmethod
    def _paint_pause(painter: QPainter, color: QColor) -> None:
        painter.setBrush(color)
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(QRectF(6, 4, 4, 16), 1, 1)
        painter.drawRoundedRect(QRectF(14, 4, 4, 16), 1, 1)

    @staticmethod
    def _paint_stop(painter: QPainter, color: QColor) -> None:
        painter.setBrush(color)
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(QRectF(5, 5, 14, 14), 2, 2)

    @staticmethod
    def _paint_document(painter: QPainter, color: QColor) -> None:
        path = QPainterPath(QPointF(5, 3))
        path.lineTo(14, 3)
        path.lineTo(19, 8)
        path.lineTo(19, 21)
        path.lineTo(5, 21)
        path.closeSubpath()
        painter.drawPath(path)
        painter.drawLine(QPointF(14, 3), QPointF(14, 8))
        painter.drawLine(QPointF(14, 8), QPointF(19, 8))
        painter.drawLine(QPointF(8, 12), QPointF(16, 12))
        painter.drawLine(QPointF(8, 16), QPointF(16, 16))

    def resize_icon(self, icon: QIcon, size: int) -> QIcon:
        if icon.isNull() or size <= 0:
            return icon
        return QIcon(icon.pixmap(QSize(size, size)))

    @staticmethod
    def create_dynamic_icon(color: str, shape: str = "circle", size: int = 24) -> QIcon:
        """Create a deterministic status marker for legacy callers."""

        parsed_color = QColor(color)
        if not parsed_color.isValid() or size <= 0:
            return QIcon()
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        painter.setBrush(parsed_color)
        bounds = QRectF(2, 2, size - 4, size - 4)
        if shape == "square":
            painter.drawRoundedRect(bounds, max(1, size / 8), max(1, size / 8))
        elif shape == "triangle":
            painter.drawPolygon(
                QPolygonF(
                    [QPointF(size / 2, 2), QPointF(size - 2, size - 2), QPointF(2, size - 2)]
                )
            )
        else:
            painter.drawEllipse(bounds)
        painter.end()
        return QIcon(pixmap)
