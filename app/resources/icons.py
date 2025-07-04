import os
import logging
from typing import Optional
from PyQt5.QtGui import QIcon, QPixmap, QPainter, QColor
from PyQt5.QtCore import QSize, Qt, QPoint
from PyQt5.QtSvg import QSvgRenderer

class IconManager:
    def __init__(self, icon_dir: str):
        self.icon_dir = icon_dir
        self.icon_cache = {}
        self.current_theme = 'light'

    def get_icon(self, name: str) -> QIcon:
        """
        获取图标
        
        Args:
            name: 图标名称
            
        Returns:
            QIcon对象
        """
        if name in self.icon_cache:
            return self.icon_cache[name]
        
        icon = self._load_icon_from_file(name)
        if icon is None:
            icon = self._generate_placeholder_icon(name)
        
        self.icon_cache[name] = icon
        return icon

    def set_theme(self, theme: str):
        """
        设置当前主题
        
        Args:
            theme: 主题名称 ('light' 或 'dark')
        """
        if theme not in ('light', 'dark'):
            logging.warning(f"不支持的主题: {theme}，使用默认主题 'light'")
            theme = 'light'
        
        if theme != self.current_theme:
            self.current_theme = theme
            # 清除主题相关图标缓存
            theme_keys = [k for k in self.icon_cache if '_' in k]
            for key in theme_keys:
                del self.icon_cache[key]
            
            logging.debug(f"图标主题已设置为: {theme}")
            
            # 重新加载常用图标
            common_icons = ['open', 'save', 'export', 'settings', 'undo', 'redo', 
                          'play', 'pause', 'stop', 'next', 'previous']
            for icon_name in common_icons:
                if icon_name in self.icon_cache:
                    del self.icon_cache[icon_name]
                # 预加载常用图标
                self.get_icon(icon_name)
    
    def _load_icon_from_file(self, name: str) -> Optional[QIcon]:
        """
        从文件加载图标
        
        Args:
            name: 图标名称，不含扩展名
            
        Returns:
            QIcon对象，如果找不到图标则返回None
        """
        # 尝试不同的文件格式
        for ext in ['svg', 'png', 'jpg']:
            file_path = os.path.join(self.icon_dir, f"{name}.{ext}")
            
            if os.path.exists(file_path):
                # SVG格式特殊处理
                if ext == 'svg':
                    return self._load_svg_icon(file_path)
                else:
                    return QIcon(file_path)
        
        return None
    
    def _load_svg_icon(self, file_path: str) -> QIcon:
        """
        加载SVG图标并处理颜色
        
        Args:
            file_path: SVG文件路径
            
        Returns:
            QIcon对象
        """
        icon = QIcon()
        
        # 常用图标尺寸
        for size in [16, 24, 32, 48, 64]:
            pixmap = QPixmap(size, size)
            pixmap.fill(Qt.GlobalColor.transparent)
            
            renderer = QSvgRenderer(file_path)
            painter = QPainter(pixmap)
            renderer.render(painter)
            painter.end()
            
            icon.addPixmap(pixmap)
        
        return icon
    
    def _generate_placeholder_icon(self, name: str) -> QIcon:
        """
        生成占位图标
        
        Args:
            name: 图标名称
            
        Returns:
            QIcon对象
        """
        # 创建彩色占位符
        icon = QIcon()
        
        # 使用图标名称的哈希值生成颜色，确保相同名称有相同颜色
        hue = hash(name) % 360
        color = QColor()
        color.setHsv(hue, 200, 200)
        
        # 创建占位图像
        for size in [16, 24, 32, 48]:
            pixmap = QPixmap(size, size)
            pixmap.fill(Qt.GlobalColor.transparent)
            
            painter = QPainter(pixmap)
            painter.setPen(Qt.GlobalColor.black)
            painter.setBrush(color)
            painter.drawRect(1, 1, size-2, size-2)
            
            # 绘制首字母
            painter.setPen(Qt.GlobalColor.white)
            font = painter.font()
            font.setPixelSize(size // 2)
            painter.setFont(font)
            
            first_letter = name[0].upper() if name else '?'
            painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, first_letter)
            
            painter.end()
            
            icon.addPixmap(pixmap)
        
        return icon
    
    def resize_icon(self, icon: QIcon, size: int) -> QIcon:
        """
        调整图标大小
        
        Args:
            icon: 源图标
            size: 目标大小
            
        Returns:
            调整大小后的图标
        """
        if not icon:
            return icon
            
        pixmap = icon.pixmap(QSize(size, size))
        return QIcon(pixmap)
    
    def create_dynamic_icon(self, color: str, shape: str = 'circle', size: int = 24) -> QIcon:
        """
        创建动态图标
        
        Args:
            color: 颜色（十六进制）
            shape: 形状 ('circle', 'square', 'triangle')
            size: 图标大小
            
        Returns:
            QIcon对象
        """
        icon = QIcon()
        
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)
        
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # 设置颜色
        color_obj = QColor(color)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color_obj)
        
        # 绘制形状
        if shape == 'circle':
            painter.drawEllipse(2, 2, size-4, size-4)
        elif shape == 'square':
            painter.drawRect(2, 2, size-4, size-4)
        elif shape == 'triangle':
            points = [
                QPoint(size//2, 2),
                QPoint(size-2, size-2),
                QPoint(2, size-2)
            ]
            painter.drawPolygon(points)
        else:
            painter.drawEllipse(2, 2, size-4, size-4)
        
        painter.end()
        
        icon.addPixmap(pixmap)
        return icon