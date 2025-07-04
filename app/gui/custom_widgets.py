"""
自定义GUI控件模块，包含项目中使用的特殊控件
"""
from PyQt5.QtWidgets import (QWidget, QPushButton, QSlider, QLabel, 
                             QLineEdit, QTextEdit, QVBoxLayout, QHBoxLayout)
from PyQt5.QtCore import Qt, pyqtSignal, QRectF, QPoint, QSize
from PyQt5.QtGui import QPainter, QPen, QColor, QBrush, QFont

class TimestampEdit(QLineEdit):
    """时间戳编辑控件"""
    valueChanged = pyqtSignal(int)  # 毫秒为单位
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setInputMask("99:99:99,999")
        self.setText("00:00:00,000")
        self.textChanged.connect(self._on_text_changed)
        
    def _on_text_changed(self, text):
        ms = self.get_milliseconds()
        self.valueChanged.emit(ms)
    
    def set_milliseconds(self, ms):
        """设置时间戳（毫秒）"""
        total_seconds = ms // 1000
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60
        milliseconds = ms % 1000
        
        self.setText(f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}")
    
    def get_milliseconds(self):
        """获取时间戳（毫秒）"""
        try:
            parts = self.text().split(":")
            hours = int(parts[0])
            minutes = int(parts[1])
            seconds_parts = parts[2].split(",")
            seconds = int(seconds_parts[0])
            milliseconds = int(seconds_parts[1])
            
            return (hours * 3600 + minutes * 60 + seconds) * 1000 + milliseconds
        except (ValueError, IndexError):
            return 0

class SubtitleTextEdit(QTextEdit):
    """字幕文本编辑控件，支持特殊格式化和自动换行"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptRichText(False)
        self.setLineWrapMode(QTextEdit.WidgetWidth)

class TimelineWidget(QWidget):
    """时间轴控件，用于显示视频时间线和字幕段落位置"""
    
    # 信号定义
    positionChanged = pyqtSignal(float)  # 当用户改变位置时发出
    segmentSelected = pyqtSignal(int)    # 当选择某个字幕段落时发出
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.segments = []
        self.duration = 0.0
        self.position = 0.0
        self.selected_segment = -1
        
        # 设置最小高度
        self.setMinimumHeight(50)
        
        # 颜色定义
        self.bg_color = QColor(40, 40, 40)
        self.timeline_color = QColor(100, 100, 100)
        self.segment_color = QColor(80, 120, 200, 180)
        self.selected_segment_color = QColor(120, 180, 255)
        self.position_color = QColor(255, 50, 50)
        
        self.setMouseTracking(True)
    
    def set_segments(self, segments):
        """设置要显示的字幕段落"""
        self.segments = segments
        self.update()
    
    def set_duration(self, total_seconds):
        """设置视频总时长"""
        self.duration = max(0.1, total_seconds)  # 避免除以零错误
        self.update()
    
    def set_position(self, position_seconds):
        """设置当前播放位置"""
        old_position = self.position
        self.position = max(0, min(position_seconds, self.duration))
        
        # 只在位置变化时重绘
        if abs(old_position - self.position) > 0.01:
            self.update()
    
    def set_selected_segment(self, index):
        """设置选中的段落索引"""
        if index != self.selected_segment:
            self.selected_segment = index
            self.update()
    
    def paintEvent(self, event):
        """绘制时间轴和字幕段落"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # 绘制背景
        painter.fillRect(event.rect(), self.bg_color)
        
        width = self.width()
        height = self.height()
        
        # 边距
        margin = 10
        inner_width = width - 2 * margin
        
        # 绘制时间轴基线
        timeline_y = height // 2
        painter.setPen(QPen(self.timeline_color, 1))
        painter.drawLine(margin, timeline_y, width - margin, timeline_y)
        
        # 如果没有持续时间，不继续绘制
        if self.duration <= 0:
            return
        
        # 绘制字幕段落
        for i, segment in enumerate(self.segments):
            # 计算段落在时间轴上的位置
            start_x = margin + (segment.start_time / self.duration) * inner_width
            end_x = margin + (segment.end_time / self.duration) * inner_width
            segment_width = max(1, end_x - start_x)
            
            # 选择颜色
            if i == self.selected_segment:
                painter.setBrush(QBrush(self.selected_segment_color))
            else:
                painter.setBrush(QBrush(self.segment_color))
            
            # 绘制段落矩形
            segment_height = height * 0.4
            segment_top = timeline_y - segment_height / 2
            painter.setPen(Qt.NoPen)
            painter.drawRoundedRect(QRectF(start_x, segment_top, segment_width, segment_height), 2, 2)
            
            # 绘制段落索引
            if segment_width > 15:  # 只有当足够宽才显示索引
                painter.setPen(QColor(255, 255, 255))
                painter.setFont(QFont("Arial", 8))
                painter.drawText(QRectF(start_x, segment_top, segment_width, segment_height), 
                                Qt.AlignCenter, str(i + 1))
        
        # 绘制当前位置指示器
        position_x = margin + (self.position / self.duration) * inner_width
        
        painter.setPen(QPen(self.position_color, 2))
        painter.drawLine(int(position_x), 5, int(position_x), height - 5)
        
        # 绘制位置指示器顶部的小三角形
        painter.setBrush(QBrush(self.position_color))
        painter.setPen(Qt.NoPen)
        
        triangle_size = 8
        triangle = [
            QPoint(int(position_x), 5),
            QPoint(int(position_x - triangle_size/2), 5 - triangle_size),
            QPoint(int(position_x + triangle_size/2), 5 - triangle_size)
        ]
        painter.drawPolygon(triangle)
        
        # 绘制时间标记
        painter.setPen(QColor(200, 200, 200))
        painter.setFont(QFont("Arial", 7))
        
        time_interval = self._calculate_time_interval()
        current_time = 0
        while current_time <= self.duration:
            x = margin + (current_time / self.duration) * inner_width
            painter.drawLine(int(x), timeline_y - 3, int(x), timeline_y + 3)
            
            # 格式化时间显示
            minutes = int(current_time / 60)
            seconds = int(current_time % 60)
            time_text = f"{minutes}:{seconds:02d}"
            
            painter.drawText(QRectF(x - 20, timeline_y + 5, 40, 15), 
                            Qt.AlignCenter, time_text)
            
            current_time += time_interval
    
    def _calculate_time_interval(self):
        """根据总时长计算合适的时间标记间隔"""
        # 希望在时间轴上标记5-10个时间点
        target_marks = 8
        
        if self.duration <= 30:
            return 5  # 5秒间隔
        elif self.duration <= 60:
            return 10  # 10秒间隔
        elif self.duration <= 300:  # 5分钟
            return 30  # 30秒间隔
        elif self.duration <= 600:  # 10分钟
            return 60  # 1分钟间隔
        elif self.duration <= 1800:  # 30分钟
            return 180  # 3分钟间隔
        else:
            return 300  # 5分钟间隔
    
    def mousePressEvent(self, event):
        """处理鼠标点击事件"""
        if event.button() == Qt.LeftButton:
            x_pos = event.x()
            width = self.width()
            margin = 10
            inner_width = width - 2 * margin
            
            # 检查是否点击了字幕段落
            clicked_segment = -1
            for i, segment in enumerate(self.segments):
                start_x = margin + (segment.start_time / self.duration) * inner_width
                end_x = margin + (segment.end_time / self.duration) * inner_width
                
                # 检查点击是否在这个段落内
                if start_x <= x_pos <= end_x:
                    clicked_segment = i
                    break
            
            if clicked_segment >= 0:
                # 点击了一个段落
                self.segmentSelected.emit(clicked_segment)
            else:
                # 点击了时间轴
                relative_pos = (x_pos - margin) / inner_width
                new_position = relative_pos * self.duration
                
                # 发出位置变化信号
                self.positionChanged.emit(max(0, min(new_position, self.duration)))
    
    def mouseMoveEvent(self, event):
        """处理鼠标移动事件"""
        if event.buttons() & Qt.LeftButton:
            # 如果是拖动，更新位置
            x_pos = event.x()
            width = self.width()
            margin = 10
            inner_width = width - 2 * margin
            
            relative_pos = (x_pos - margin) / inner_width
            new_position = relative_pos * self.duration
            
            # 发出位置变化信号
            self.positionChanged.emit(max(0, min(new_position, self.duration)))
        else:
            # 更新鼠标悬停效果
            self.update()
    
    def sizeHint(self):
        """返回建议的控件大小"""
        return QSize(600, 50)

class WaveformView(QWidget):
    """音频波形显示控件，用于可视化视频的音频波形"""
    
    positionChanged = pyqtSignal(float)  # 当用户改变位置时发出
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.waveform_data = []  # 存储波形数据
        self.duration = 0.0
        self.position = 0.0
        
        # 设置最小高度
        self.setMinimumHeight(80)
        
        # 颜色定义
        self.bg_color = QColor(30, 30, 30)
        self.waveform_color = QColor(100, 180, 100)
        self.position_color = QColor(255, 50, 50)
        
        self.setMouseTracking(True)
    
    def set_waveform_data(self, data):
        """设置波形数据"""
        self.waveform_data = data
        self.update()
    
    def set_duration(self, total_seconds):
        """设置音频总时长"""
        self.duration = max(0.1, total_seconds)
        self.update()
    
    def set_position(self, position_seconds):
        """设置当前播放位置"""
        old_position = self.position
        self.position = max(0, min(position_seconds, self.duration))
        
        # 只在位置变化时重绘
        if abs(old_position - self.position) > 0.01:
            self.update()
    
    def paintEvent(self, event):
        """绘制波形"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # 绘制背景
        painter.fillRect(event.rect(), self.bg_color)
        
        width = self.width()
        height = self.height()
        
        # 如果有波形数据，绘制波形
        if self.waveform_data and self.duration > 0:
            painter.setPen(QPen(self.waveform_color, 1))
            
            # 为简化实现，这里假设waveform_data是一个振幅值数组
            # 实际使用中应替换为实际的波形数据处理
            center_y = height // 2
            
            for i in range(len(self.waveform_data) - 1):
                x1 = i * width / len(self.waveform_data)
                x2 = (i + 1) * width / len(self.waveform_data)
                
                amp1 = self.waveform_data[i] * height / 2
                amp2 = self.waveform_data[i + 1] * height / 2
                
                y1 = center_y - amp1
                y2 = center_y - amp2
                
                painter.drawLine(int(x1), int(y1), int(x2), int(y2))
                painter.drawLine(int(x1), int(center_y + amp1), int(x2), int(center_y + amp2))
        else:
            # 如果没有波形数据，绘制一个提示文本
            painter.setPen(QColor(150, 150, 150))
            painter.setFont(QFont("Arial", 10))
            painter.drawText(event.rect(), Qt.AlignCenter, "波形数据未加载")
        
        # 绘制当前位置指示器
        if self.duration > 0:
            position_x = (self.position / self.duration) * width
            
            painter.setPen(QPen(self.position_color, 2))
            painter.drawLine(int(position_x), 0, int(position_x), height)
    
    def mousePressEvent(self, event):
        """处理鼠标点击事件"""
        if event.button() == Qt.LeftButton:
            x_pos = event.x()
            width = self.width()
            
            # 计算对应的时间位置
            relative_pos = x_pos / width
            new_position = relative_pos * self.duration
            
            # 发出位置变化信号
            self.positionChanged.emit(max(0, min(new_position, self.duration)))
    
    def mouseMoveEvent(self, event):
        """处理鼠标移动事件"""
        if event.buttons() & Qt.LeftButton:
            # 如果是拖动，更新位置
            x_pos = event.x()
            width = self.width()
            
            # 计算对应的时间位置
            relative_pos = x_pos / width
            new_position = relative_pos * self.duration
            
            # 发出位置变化信号
            self.positionChanged.emit(max(0, min(new_position, self.duration)))
    
    def sizeHint(self):
        """返回建议的控件大小"""
        return QSize(600, 80)