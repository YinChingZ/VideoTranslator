import logging
import platform
from typing import Dict, Any, Optional
from PyQt5.QtWidgets import QApplication, QWidget
from PyQt5.QtGui import QPalette, QColor

# 定义颜色方案常量
LIGHT_THEME = {
    'primary': '#3498db',      # 主色
    'secondary': '#2ecc71',    # 次要色
    'background': '#f5f5f5',   # 背景色
    'text': '#333333',         # 文本色
    'accent': '#9b59b6',       # 强调色
    'warning': '#f39c12',      # 警告色
    'error': '#e74c3c',        # 错误色
    'success': '#2ecc71',      # 成功色
}

DARK_THEME = {
    'primary': '#3498db',      # 主色
    'secondary': '#2ecc71',    # 次要色
    'background': '#2c3e50',   # 背景色
    'text': '#ecf0f1',         # 文本色
    'accent': '#9b59b6',       # 强调色
    'warning': '#f39c12',      # 警告色
    'error': '#e74c3c',        # 错误色
    'success': '#2ecc71',      # 成功色
}

class StyleManager:
    """样式管理器，负责应用程序样式和主题"""
    
    def __init__(self):
        """初始化样式管理器"""
        self.current_theme = 'light'
        self.system_name = platform.system()
    
    def apply_light_theme(self, widget=None):
        """应用浅色主题"""
        self.current_theme = 'light'
        stylesheet = self._generate_stylesheet(LIGHT_THEME)
        self._apply_stylesheet(stylesheet, widget)
        
        if widget is None:
            self._set_application_palette(light=True)
    
    def apply_dark_theme(self, widget=None):
        """应用深色主题"""
        self.current_theme = 'dark'
        stylesheet = self._generate_stylesheet(DARK_THEME)
        self._apply_stylesheet(stylesheet, widget)
        
        if widget is None:
            self._set_application_palette(light=False)
    
    def toggle_theme(self, widget=None):
        """切换当前主题"""
        if self.current_theme == 'light':
            self.apply_dark_theme(widget)
        else:
            self.apply_light_theme(widget)
    
    def _generate_stylesheet(self, colors: Dict[str, str]) -> str:
        """
        根据颜色方案生成样式表
        
        Args:
            colors: 颜色方案词典
            
        Returns:
            生成的CSS样式表
        """
        primary = colors['primary']
        secondary = colors['secondary']
        background = colors['background']
        text = colors['text']
        accent = colors['accent']
        warning = colors['warning']
        error = colors['error']
        
        # 判断背景色是深色还是浅色
        is_dark_bg = self._is_dark_color(background)
        border_color = '#555555' if is_dark_bg else '#cccccc'
        hover_bg = self._adjust_brightness(background, -20 if is_dark_bg else 20)
        
        # 基本样式表
        stylesheet = f"""
        /* 全局样式 */
        QWidget {{
            background-color: {background};
            color: {text};
            font-family: Arial, Helvetica, sans-serif;
        }}
        
        /* 按钮样式 */
        QPushButton {{
            background-color: {primary};
            color: white;
            border: none;
            padding: 8px 16px;
            border-radius: 4px;
            min-width: 80px;
        }}
        
        QPushButton:hover {{
            background-color: {self._adjust_brightness(primary, -20)};
        }}
        
        QPushButton:pressed {{
            background-color: {self._adjust_brightness(primary, -40)};
        }}
        
        QPushButton:disabled {{
            background-color: {self._adjust_brightness(background, 20 if is_dark_bg else -20)};
            color: {self._adjust_brightness(text, 40 if is_dark_bg else -40)};
        }}
        
        /* 次要按钮 */
        QPushButton[secondary="true"] {{
            background-color: {secondary};
            color: white;
        }}
        
        QPushButton[secondary="true"]:hover {{
            background-color: {self._adjust_brightness(secondary, -20)};
        }}
        
        /* 文本框样式 */
        QLineEdit, QTextEdit, QPlainTextEdit {{
            background-color: {self._adjust_brightness(background, 10 if is_dark_bg else -10)};
            color: {text};
            border: 1px solid {border_color};
            border-radius: 4px;
            padding: 4px;
        }}
        
        QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {{
            border: 2px solid {primary};
        }}
        
        /* 标签样式 */
        QLabel {{
            color: {text};
            background-color: transparent;
        }}
        
        /* 标题标签 */
        QLabel[heading="true"] {{
            font-size: 16pt;
            font-weight: bold;
            color: {primary};
        }}
        
        /* 下拉菜单 */
        QComboBox {{
            background-color: {self._adjust_brightness(background, 10 if is_dark_bg else -10)};
            color: {text};
            border: 1px solid {border_color};
            border-radius: 4px;
            padding: 4px;
            min-width: 100px;
        }}
        
        QComboBox:hover {{
            border: 1px solid {primary};
        }}
        
        QComboBox::drop-down {{
            border: none;
            width: 20px;
        }}
        
        /* 滑块 */
        QSlider::groove:horizontal {{
            border: 1px solid {border_color};
            height: 4px;
            background: {self._adjust_brightness(background, 10 if is_dark_bg else -10)};
            border-radius: 2px;
        }}
        
        QSlider::handle:horizontal {{
            background: {primary};
            border: 1px solid {primary};
            width: 16px;
            height: 16px;
            margin: -6px 0;
            border-radius: 8px;
        }}
        
        /* 进度条 */
        QProgressBar {{
            border: 1px solid {border_color};
            border-radius: 4px;
            background-color: {self._adjust_brightness(background, 10 if is_dark_bg else -10)};
            text-align: center;
        }}
        
        QProgressBar::chunk {{
            background-color: {primary};
            width: 1px;
        }}
        
        /* 多选框 */
        QCheckBox {{
            spacing: 5px;
        }}
        
        QCheckBox::indicator {{
            width: 18px;
            height: 18px;
        }}
        
        QCheckBox::indicator:unchecked {{
            border: 1px solid {border_color};
            background-color: {self._adjust_brightness(background, 10 if is_dark_bg else -10)};
        }}
        
        QCheckBox::indicator:checked {{
            border: 1px solid {primary};
            background-color: {primary};
            image: url(:/icons/check_white.png);
        }}
        
        /* 单选按钮 */
        QRadioButton {{
            spacing: 5px;
        }}
        
        QRadioButton::indicator {{
            width: 18px;
            height: 18px;
            border-radius: 9px;
        }}
        
        QRadioButton::indicator:unchecked {{
            border: 1px solid {border_color};
            background-color: {self._adjust_brightness(background, 10 if is_dark_bg else -10)};
        }}
        
        QRadioButton::indicator:checked {{
            border: 1px solid {primary};
            background-color: {primary};
        }}
        
        /* 菜单样式 */
        QMenuBar {{
            background-color: {background};
            color: {text};
        }}
        
        QMenuBar::item:selected {{
            background-color: {primary};
            color: white;
        }}
        
        QMenu {{
            background-color: {background};
            color: {text};
            border: 1px solid {border_color};
        }}
        
        QMenu::item:selected {{
            background-color: {primary};
            color: white;
        }}
        
        /* 工具栏样式 */
        QToolBar {{
            background-color: {background};
            border-bottom: 1px solid {border_color};
            spacing: 6px;
        }}
        
        /* 状态栏样式 */
        QStatusBar {{
            background-color: {self._adjust_brightness(background, -10 if is_dark_bg else 10)};
            color: {text};
        }}
        
        /* 选项卡样式 */
        QTabWidget::pane {{
            border: 1px solid {border_color};
            border-top: 0px;
        }}
        
        QTabBar::tab {{
            background-color: {self._adjust_brightness(background, -10 if is_dark_bg else 10)};
            color: {text};
            border: 1px solid {border_color};
            padding: 6px 12px;
        }}
        
        QTabBar::tab:selected {{
            background-color: {primary};
            color: white;
            border-bottom: 0px;
        }}
        
        /* 滚动条样式 */
        QScrollBar:vertical {{
            border: none;
            background-color: {self._adjust_brightness(background, 10 if is_dark_bg else -10)};
            width: 12px;
            border-radius: 6px;
            margin: 12px 0;
        }}
        
        QScrollBar::handle:vertical {{
            background-color: {self._adjust_brightness(primary, 20)};
            border-radius: 6px;
            min-height: 20px;
        }}
        
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
            border: none;
            background: none;
        }}
        
        QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
            background: none;
        }}
        
        /* 水平滚动条 */
        QScrollBar:horizontal {{
            border: none;
            background-color: {self._adjust_brightness(background, 10 if is_dark_bg else -10)};
            height: 12px;
            border-radius: 6px;
            margin: 0 12px;
        }}
        
        QScrollBar::handle:horizontal {{
            background-color: {self._adjust_brightness(primary, 20)};
            border-radius: 6px;
            min-width: 20px;
        }}
        
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
            border: none;
            background: none;
        }}
        
        QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
            background: none;
        }}
        
        /* 自定义视频导入页面 */
        #videoImportWidget {{
            background-color: {background};
        }}
        
        #dropZone {{
            border: 2px dashed {border_color};
            border-radius: 8px;
            background-color: {self._adjust_brightness(background, 5 if is_dark_bg else -5)};
            padding: 20px;
        }}
        
        #dropZone:hover {{
            border-color: {primary};
        }}
        
        /* 自定义处理页面 */
        .ProcessingWidget {{
            background-color: {background};
        }}
        
        .ProcessingWidget QLabel[stage="complete"] {{
            color: {colors['success']};
        }}
        
        .ProcessingWidget QLabel[stage="error"] {{
            color: {colors['error']};
        }}
        
        .ProcessingWidget QLabel[stage="waiting"] {{
            color: {self._adjust_brightness(text, 60 if is_dark_bg else -60)};
        }}
        
        /* 自定义字幕编辑器 */
        #timelineWidget {{
            background-color: {self._adjust_brightness(background, -10 if is_dark_bg else 10)};
            border: 1px solid {border_color};
        }}
        
        #bilingualEditor {{
            background-color: {self._adjust_brightness(background, 5 if is_dark_bg else -5)};
        }}
        """
        
        # 根据操作系统添加特定样式
        if self.system_name == 'Darwin':  # macOS
            stylesheet += """
            /* macOS 特定样式 */
            QToolBar {
                border: none;
            }
            """
        elif self.system_name == 'Windows':
            stylesheet += """
            /* Windows 特定样式 */
            QWidget {
                font-family: 'Segoe UI', Arial, sans-serif;
            }
            """
        
        return stylesheet
    
    def _apply_stylesheet(self, stylesheet: str, widget: Optional[QWidget] = None):
        """
        应用样式表到小部件或应用程序
        
        Args:
            stylesheet: CSS样式表
            widget: 目标小部件，如为None则应用到整个应用程序
        """
        try:
            if widget is None:
                QApplication.instance().setStyleSheet(stylesheet)
            else:
                widget.setStyleSheet(stylesheet)
                
            logging.debug(f"已应用 {self.current_theme} 主题样式表")
        except Exception as e:
            logging.error(f"应用样式表失败: {str(e)}")
    
    def _set_application_palette(self, light: bool = True):
        """
        设置应用程序调色板
        
        Args:
            light: 是否使用浅色调色板
        """
        try:
            app = QApplication.instance()
            if not app:
                return
                
            palette = QPalette()
            
            if light:
                # 浅色主题调色板
                palette.setColor(QPalette.ColorRole.Window, QColor("#f5f5f5"))
                palette.setColor(QPalette.ColorRole.WindowText, QColor("#333333"))
                palette.setColor(QPalette.ColorRole.Base, QColor("#ffffff"))
                palette.setColor(QPalette.ColorRole.AlternateBase, QColor("#e9e9e9"))
                palette.setColor(QPalette.ColorRole.Text, QColor("#333333"))
                palette.setColor(QPalette.ColorRole.Button, QColor("#f5f5f5"))
                palette.setColor(QPalette.ColorRole.ButtonText, QColor("#333333"))
                palette.setColor(QPalette.ColorRole.BrightText, QColor("#ffffff"))
                palette.setColor(QPalette.ColorRole.Highlight, QColor("#3498db"))
                palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
            else:
                # 深色主题调色板
                palette.setColor(QPalette.ColorRole.Window, QColor("#2c3e50"))
                palette.setColor(QPalette.ColorRole.WindowText, QColor("#ecf0f1"))
                palette.setColor(QPalette.ColorRole.Base, QColor("#34495e"))
                palette.setColor(QPalette.ColorRole.AlternateBase, QColor("#3d566e"))
                palette.setColor(QPalette.ColorRole.Text, QColor("#ecf0f1"))
                palette.setColor(QPalette.ColorRole.Button, QColor("#2c3e50"))
                palette.setColor(QPalette.ColorRole.ButtonText, QColor("#ecf0f1"))
                palette.setColor(QPalette.ColorRole.BrightText, QColor("#ffffff"))
                palette.setColor(QPalette.ColorRole.Highlight, QColor("#3498db"))
                palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
                
            app.setPalette(palette)
        except Exception as e:
            logging.error(f"设置应用程序调色板失败: {str(e)}")
    
    @staticmethod
    def _is_dark_color(hex_color: str) -> bool:
        """
        判断颜色是否为深色
        
        Args:
            hex_color: 十六进制颜色代码
            
        Returns:
            如果是深色则返回True，否则返回False
        """
        # 移除井号（如果存在）
        hex_color = hex_color.lstrip('#')
        
        # 转换为RGB
        r = int(hex_color[0:2], 16)
        g = int(hex_color[2:4], 16)
        b = int(hex_color[4:6], 16)
        
        # 计算亮度
        brightness = (r * 299 + g * 587 + b * 114) / 1000
        
        # 亮度低于128认为是深色
        return brightness < 128
    
    @staticmethod
    def _adjust_brightness(hex_color: str, amount: int) -> str:
        """
        调整颜色亮度
        
        Args:
            hex_color: 十六进制颜色代码
            amount: 亮度调整量（正值增加亮度，负值减少亮度）
            
        Returns:
            调整后的十六进制颜色
        """
        # 移除井号（如果存在）
        hex_color = hex_color.lstrip('#')
        
        # 转换为RGB
        r = int(hex_color[0:2], 16)
        g = int(hex_color[2:4], 16)
        b = int(hex_color[4:6], 16)
        
        # 调整亮度
        r = max(0, min(255, r + amount))
        g = max(0, min(255, g + amount))
        b = max(0, min(255, b + amount))
        
        # 转换回十六进制
        return f"#{r:02x}{g:02x}{b:02x}"
    
    def load_font(self, font_name: str, font_path: str) -> bool:
        """
        加载自定义字体
        
        Args:
            font_name: 字体名称
            font_path: 字体文件路径
            
        Returns:
            成功则返回True，失败则返回False
        """
        from PyQt5.QtGui import QFontDatabase
        try:
            font_id = QFontDatabase.addApplicationFont(font_path)
            if font_id == -1:
                logging.error(f"加载字体失败: {font_path}")
                return False
                
            logging.debug(f"已加载字体: {font_name}")
            return True
        except Exception as e:
            logging.error(f"加载字体时发生错误: {str(e)}")
            return False
    
    def get_theme_colors(self) -> Dict[str, str]:
        """
        获取当前主题的颜色方案
        
        Returns:
            颜色方案词典
        """
        return DARK_THEME if self.current_theme == 'dark' else LIGHT_THEME
    
    def get_specific_color(self, color_name: str) -> str:
        """
        获取当前主题中特定的颜色
        
        Args:
            color_name: 颜色名称 (primary, secondary, background等)
            
        Returns:
            十六进制颜色代码
        """
        colors = self.get_theme_colors()
        return colors.get(color_name, "#000000" if self.current_theme == 'light' else "#ffffff")
    
    def get_adjusted_color_scheme(self, brightness_offset: int = 0) -> Dict[str, str]:
        """
        获取亮度调整后的颜色方案
        
        Args:
            brightness_offset: 亮度调整量
            
        Returns:
            调整后的颜色方案词典
        """
        colors = self.get_theme_colors()
        adjusted_colors = {}
        
        for name, color in colors.items():
            adjusted_colors[name] = self._adjust_brightness(color, brightness_offset)
            
        return adjusted_colors
    
    def get_custom_theme(self, primary_color: str) -> Dict[str, str]:
        """
        基于主色创建自定义主题
        
        Args:
            primary_color: 十六进制主色
            
        Returns:
            自定义主题颜色方案
        """
        # 从当前主题复制颜色方案
        custom_theme = self.get_theme_colors().copy()
        
        # 设置新的主色
        custom_theme['primary'] = primary_color
        
        # 根据主色调整其他颜色
        is_dark = self._is_dark_color(primary_color)
        
        # 如果主色是深色但当前是浅色主题，或主色是浅色但当前是深色主题
        # 可能需要调整其他颜色
        if is_dark and self.current_theme == 'light':
            # 调整次要色为主色的较亮版本
            custom_theme['secondary'] = self._adjust_brightness(primary_color, 40)
        elif not is_dark and self.current_theme == 'dark':
            # 调整次要色为主色的较暗版本
            custom_theme['secondary'] = self._adjust_brightness(primary_color, -40)
        
        return custom_theme
