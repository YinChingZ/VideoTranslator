import os
import logging
from typing import Optional, Dict, Any
from pathlib import Path

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox,
    QFileDialog, QProgressBar, QFrame, QSizePolicy, QSpacerItem,
    QGridLayout, QFormLayout
)
from PyQt5.QtCore import Qt, QSize, pyqtSignal, QMimeData, QUrl
from PyQt5.QtGui import QPixmap, QDragEnterEvent, QDragLeaveEvent, QDropEvent, QImageReader

from app.core.video import VideoProcessor
from app.resources.icons import IconManager

class DropZone(QLabel):
    """支持拖放功能的QLabel"""
    
    file_dropped = pyqtSignal(str)  # 当文件被拖放时发出信号
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setText("将视频文件拖放到这里\n或点击选择文件")
        self.setMinimumSize(400, 200)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setFrameStyle(QFrame.Shape.StyledPanel | QFrame.Shadow.Sunken)
        self.setObjectName("dropZone")
        
        # 启用拖放
        self.setAcceptDrops(True)
    
    def dragEnterEvent(self, event: QDragEnterEvent):
        """处理拖拽进入事件"""
        mime_data = event.mimeData()
        
        # 检查是否是文件URL
        if mime_data.hasUrls():
            for url in mime_data.urls():
                if url.isLocalFile():
                    file_path = url.toLocalFile()
                    ext = os.path.splitext(file_path)[1].lower()
                    
                    # 检查是否是视频文件
                    if ext in ['.mp4', '.mkv', '.avi', '.mov', '.webm', '.flv', '.wmv']:
                        event.acceptProposedAction()
                        self.setStyleSheet("border: 2px solid #3498db;")
                        return
        
        event.ignore()
    
    def dragLeaveEvent(self, event: QDragLeaveEvent):
        """处理拖拽离开事件"""
        self.setStyleSheet("")
        event.accept()
    
    def dropEvent(self, event: QDropEvent):
        """处理拖放事件"""
        mime_data = event.mimeData()
        
        if mime_data.hasUrls():
            for url in mime_data.urls():
                if url.isLocalFile():
                    file_path = url.toLocalFile()
                    ext = os.path.splitext(file_path)[1].lower()
                    
                    if ext in ['.mp4', '.mkv', '.avi', '.mov', '.webm', '.flv', '.wmv']:
                        self.file_dropped.emit(file_path)
                        event.acceptProposedAction()
                        self.setStyleSheet("")
                        return
        
        event.ignore()
    
    def mousePressEvent(self, event):
        """处理鼠标点击事件"""
        self.parent().browse_video()
        super().mousePressEvent(event)

class VideoImportWidget(QWidget):
    """视频导入界面"""
    
    # 信号：当用户点击继续按钮时发出
    continue_signal = pyqtSignal()
    
    def __init__(self, config: Dict[str, Any], parent=None):
        super().__init__(parent)
        self.config = config
        self.video_path = None
        self.video_processor = VideoProcessor()

        script_dir = os.path.dirname(os.path.abspath(__file__))  # 当前文件所在目录
        project_root = os.path.dirname(os.path.dirname(script_dir))  # 项目根目录
        icons_dir = os.path.join(project_root, "app", "resources", "icons")
        self.icon_manager = IconManager(icons_dir)
        
        self.setup_ui()
        self.setup_connections()
        
        # 初始隐藏视频信息面板
        self.video_info_frame.setVisible(False)
    
    def setup_ui(self):
        """设置用户界面"""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(20)
        
        # 标题
        title_label = QLabel("导入视频")
        title_label.setProperty("heading", True)
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(title_label)
        
        # 拖放区域
        self.drop_zone = DropZone(self)
        main_layout.addWidget(self.drop_zone, 1)
        
        # 视频信息框架
        self.video_info_frame = QFrame()
        self.video_info_frame.setFrameStyle(QFrame.Shape.StyledPanel | QFrame.Shadow.Raised)
        video_info_layout = QGridLayout(self.video_info_frame)
        
        # 缩略图
        self.thumbnail_label = QLabel()
        self.thumbnail_label.setFixedSize(240, 135)  # 16:9 宽高比
        self.thumbnail_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.thumbnail_label.setStyleSheet("background-color: #333;")
        video_info_layout.addWidget(self.thumbnail_label, 0, 0, 3, 1)
        
        # 视频信息
        self.filename_label = QLabel()
        self.duration_label = QLabel()
        self.resolution_label = QLabel()
        
        info_layout = QFormLayout()
        info_layout.addRow("文件名:", self.filename_label)
        info_layout.addRow("时长:", self.duration_label)
        info_layout.addRow("分辨率:", self.resolution_label)
        
        video_info_layout.addLayout(info_layout, 0, 1, 3, 1)
        main_layout.addWidget(self.video_info_frame)
        
        # 选择语言
        lang_layout = QHBoxLayout()
        
        source_lang_label = QLabel("源语言:")
        self.source_lang_combo = QComboBox()
        self.source_lang_combo.addItem("自动检测", "auto")
        
        target_lang_label = QLabel("目标语言:")
        self.target_lang_combo = QComboBox()
        
        # 填充语言选项
        for code, name in self.config.get("language_codes", {}).items():
            self.source_lang_combo.addItem(name, code)
            self.target_lang_combo.addItem(name, code)
        
        # 设置默认目标语言
        default_target = self.config.get("default_target_language", "zh-CN")
        for i in range(self.target_lang_combo.count()):
            if self.target_lang_combo.itemData(i) == default_target:
                self.target_lang_combo.setCurrentIndex(i)
                break
        
        lang_layout.addWidget(source_lang_label)
        lang_layout.addWidget(self.source_lang_combo)
        lang_layout.addSpacing(20)
        lang_layout.addWidget(target_lang_label)
        lang_layout.addWidget(self.target_lang_combo)
        
        main_layout.addLayout(lang_layout)
        
        # 按钮
        btn_layout = QHBoxLayout()
        btn_layout.addStretch(1)
        
        self.browse_btn = QPushButton("浏览...")
        self.browse_btn.setIcon(self.icon_manager.get_icon("open"))
        
        self.continue_btn = QPushButton("继续")
        self.continue_btn.setIcon(self.icon_manager.get_icon("next"))
        self.continue_btn.setEnabled(False)  # 初始禁用
        
        btn_layout.addWidget(self.browse_btn)
        btn_layout.addWidget(self.continue_btn)
        
        main_layout.addLayout(btn_layout)
    
    def setup_connections(self):
        """设置信号和槽连接"""
        self.browse_btn.clicked.connect(self.browse_video)
        self.continue_btn.clicked.connect(self.continue_signal)
        self.drop_zone.file_dropped.connect(self.set_video_path)
    
    def browse_video(self):
        """打开文件对话框选择视频"""
        file_filter = "视频文件 ({});;所有文件 (*)".format(
            " ".join(f"*.{ext}" for ext in self.config.get("supported_video_formats", 
                                                       ["mp4", "mkv", "avi", "mov", "webm", "flv", "wmv"])))
        
        filepath, _ = QFileDialog.getOpenFileName(
            self, 
            "选择视频文件", 
            self.config.get("last_directory", os.path.expanduser("~")),
            file_filter
        )
        
        if filepath:
            self.set_video_path(filepath)
    
    def set_video_path(self, filepath: str):
        """设置视频路径并更新界面"""
        if not os.path.exists(filepath):
            logging.error(f"文件不存在: {filepath}")
            return
        
        self.video_path = filepath
        
        # 保存目录到配置
        self.config["last_directory"] = os.path.dirname(filepath)
        
        # 加载视频信息
        self.load_video_info()
        
        # 启用继续按钮
        self.continue_btn.setEnabled(True)
        
        # 显示视频信息面板
        self.video_info_frame.setVisible(True)
        
        # 更新拖放区域
        self.drop_zone.setText(f"当前文件: {os.path.basename(filepath)}\n\n拖放新文件可替换")
    
    def load_video_info(self):
        """加载视频信息和缩略图"""
        try:
            # 获取视频信息
            info = self.video_processor.get_video_info(self.video_path)
            
            # 更新界面
            self.filename_label.setText(info.get('filename', '未知'))
            
            # 格式化时长
            duration_sec = info.get('duration', 0)
            hours = int(duration_sec // 3600)
            minutes = int((duration_sec % 3600) // 60)
            seconds = int(duration_sec % 60)
            self.duration_label.setText(f"{hours:02d}:{minutes:02d}:{seconds:02d}")
            
            # 分辨率
            width = info.get('width', 0)
            height = info.get('height', 0)
            self.resolution_label.setText(f"{width}x{height}")
            
            # 生成缩略图
            self.generate_thumbnail()
            
        except Exception as e:
            logging.error(f"加载视频信息失败: {str(e)}")
            self.filename_label.setText(os.path.basename(self.video_path))
            self.duration_label.setText("未知")
            self.resolution_label.setText("未知")
    
    def generate_thumbnail(self):
        """生成并显示视频缩略图"""
        try:
            # 生成缩略图
            thumbnail_path = self.video_processor.generate_thumbnail(self.video_path)
            
            if thumbnail_path and os.path.exists(thumbnail_path):
                # 加载缩略图
                pixmap = QPixmap(thumbnail_path)
                
                # 缩放以适应标签大小
                pixmap = pixmap.scaled(
                    self.thumbnail_label.size(),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
                )
                
                self.thumbnail_label.setPixmap(pixmap)
                
                # 缩略图是临时文件，可以删除
                os.remove(thumbnail_path)
            else:
                # 如果生成失败，显示占位图像
                self.thumbnail_label.setText("无法生成预览")
                
        except Exception as e:
            logging.error(f"生成缩略图失败: {str(e)}")
            self.thumbnail_label.setText("预览不可用")
    
    def get_source_language(self) -> str:
        """获取选择的源语言代码"""
        return self.source_lang_combo.currentData()
    
    def get_target_language(self) -> str:
        """获取选择的目标语言代码"""
        return self.target_lang_combo.currentData()
