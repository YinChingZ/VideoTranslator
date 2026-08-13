import logging
import os
from dataclasses import dataclass
from typing import Any, Dict, Optional

from PyQt5.QtCore import QObject, QRunnable, Qt, QThreadPool, pyqtSignal, pyqtSlot
from PyQt5.QtGui import (
    QDragEnterEvent,
    QDragLeaveEvent,
    QDropEvent,
    QKeyEvent,
    QMouseEvent,
    QPixmap,
)
from PyQt5.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.core.video import VideoProcessor
from app.resources.icons import IconManager


@dataclass(frozen=True)
class _VideoLoadResult:
    request_id: int
    video_path: str
    info: Dict[str, Any]
    thumbnail_data: bytes


class _VideoLoadSignals(QObject):
    loaded = pyqtSignal(object)
    failed = pyqtSignal(int, str, str)


class _VideoLoadTask(QRunnable):
    """Probe and thumbnail a video without touching GUI objects."""

    def __init__(self, request_id: int, video_path: str, processor: VideoProcessor):
        super().__init__()
        self.request_id = request_id
        self.video_path = video_path
        self.processor = processor
        self.signals = _VideoLoadSignals()
        self.setAutoDelete(True)

    @pyqtSlot()
    def run(self) -> None:
        thumbnail_path: Optional[str] = None
        try:
            info = self.processor.get_video_info(self.video_path)
            if info.get("error"):
                raise RuntimeError(str(info["error"]))

            duration = max(0.0, float(info.get("duration", 0) or 0))
            thumbnail_path = self.processor.generate_thumbnail(
                self.video_path,
                time_pos=duration / 2,
                width=480,
            )
            thumbnail_data = b""
            if thumbnail_path and os.path.isfile(thumbnail_path):
                with open(thumbnail_path, "rb") as thumbnail_file:
                    thumbnail_data = thumbnail_file.read()

            self.signals.loaded.emit(
                _VideoLoadResult(
                    request_id=self.request_id,
                    video_path=self.video_path,
                    info=dict(info),
                    thumbnail_data=thumbnail_data,
                )
            )
        except Exception as exc:
            logging.exception("加载视频信息失败: %s", self.video_path)
            self.signals.failed.emit(self.request_id, self.video_path, str(exc))
        finally:
            if thumbnail_path:
                try:
                    os.remove(thumbnail_path)
                except FileNotFoundError:
                    pass
                except OSError:
                    logging.warning("无法删除临时缩略图: %s", thumbnail_path)


class DropZone(QLabel):
    """Accessible file drop target that also behaves like a keyboard button."""

    file_dropped = pyqtSignal(str)
    browse_requested = pyqtSignal()

    DEFAULT_EXTENSIONS = frozenset({".avi", ".flv", ".mkv", ".mov", ".mp4", ".webm", ".wmv"})

    def __init__(self, parent=None, supported_extensions=None):
        super().__init__(parent)
        extensions = supported_extensions or self.DEFAULT_EXTENSIONS
        self.supported_extensions = frozenset(
            extension.lower() if str(extension).startswith(".") else f".{str(extension).lower()}"
            for extension in extensions
        )
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setText("将视频拖放到这里\n或按 Enter 选择文件")
        self.setMinimumSize(360, 190)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setObjectName("dropZone")
        self.setProperty("dragActive", False)
        self.setAcceptDrops(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAccessibleName("视频文件导入区域")
        self.setAccessibleDescription("拖放视频文件，或按 Enter、空格键打开文件选择器")
        self.setToolTip("支持拖放；也可按 Enter 或空格键选择视频")

    def _local_video_path(self, event) -> Optional[str]:
        mime_data = event.mimeData()
        if not mime_data.hasUrls():
            return None
        for url in mime_data.urls():
            if not url.isLocalFile():
                continue
            file_path = url.toLocalFile()
            if os.path.isfile(file_path) and os.path.splitext(file_path)[1].lower() in self.supported_extensions:
                return file_path
        return None

    def _set_drag_active(self, active: bool) -> None:
        if self.property("dragActive") == active:
            return
        self.setProperty("dragActive", active)
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()

    def dragEnterEvent(self, event: QDragEnterEvent):
        if self._local_video_path(event):
            self._set_drag_active(True)
            event.acceptProposedAction()
            return
        self._set_drag_active(False)
        event.ignore()

    def dragLeaveEvent(self, event: QDragLeaveEvent):
        self._set_drag_active(False)
        event.accept()

    def dropEvent(self, event: QDropEvent):
        file_path = self._local_video_path(event)
        self._set_drag_active(False)
        if file_path:
            self.file_dropped.emit(file_path)
            event.acceptProposedAction()
            return
        event.ignore()

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self.setFocus(Qt.FocusReason.MouseFocusReason)
            self.browse_requested.emit()
            event.accept()
            return
        super().mousePressEvent(event)

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self.browse_requested.emit()
            event.accept()
            return
        super().keyPressEvent(event)

class VideoImportWidget(QWidget):
    """视频导入界面"""
    
    # 信号：当用户点击继续按钮时发出
    continue_signal = pyqtSignal()
    video_info_loaded = pyqtSignal(dict)
    video_info_error = pyqtSignal(str)
    
    def __init__(self, config: Dict[str, Any], parent=None):
        super().__init__(parent)
        self.setObjectName("videoImportWidget")
        self.config = config
        self.video_path = None
        self.video_processor = VideoProcessor()
        self.video_info: Optional[Dict[str, Any]] = None
        self._load_generation = 0
        self._active_load_tasks = set()
        self._thread_pool = QThreadPool.globalInstance()

        script_dir = os.path.dirname(os.path.abspath(__file__))  # 当前文件所在目录
        project_root = os.path.dirname(os.path.dirname(script_dir))  # 项目根目录
        icons_dir = os.path.join(project_root, "app", "resources", "icons")
        self.icon_manager = IconManager(icons_dir)
        self.icon_manager.set_theme(str(self.config.get("theme", "system")))
        
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
        title_label.setAccessibleName("导入视频")
        main_layout.addWidget(title_label)
        
        # 拖放区域
        supported_formats = self.config.get(
            "supported_video_formats",
            ["mp4", "mkv", "avi", "mov", "webm", "flv", "wmv"],
        )
        self.drop_zone = DropZone(self, supported_formats)
        main_layout.addWidget(self.drop_zone, 1)
        
        # 视频信息框架
        self.video_info_frame = QFrame()
        self.video_info_frame.setObjectName("videoInfoFrame")
        video_info_layout = QGridLayout(self.video_info_frame)
        video_info_layout.setContentsMargins(14, 14, 14, 14)
        video_info_layout.setHorizontalSpacing(18)
        
        # 缩略图
        self.thumbnail_label = QLabel()
        self.thumbnail_label.setObjectName("thumbnailPreview")
        self.thumbnail_label.setFixedSize(240, 135)  # 16:9 宽高比
        self.thumbnail_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.thumbnail_label.setText("视频预览")
        self.thumbnail_label.setAccessibleName("视频缩略图预览")
        video_info_layout.addWidget(self.thumbnail_label, 0, 0, 3, 1)
        
        # 视频信息
        self.filename_label = QLabel()
        self.duration_label = QLabel()
        self.resolution_label = QLabel()
        self.filename_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.filename_label.setWordWrap(True)
        
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
        self.source_lang_combo.setAccessibleName("源语言")
        self.source_lang_combo.addItem("自动检测", "auto")
        source_lang_label.setBuddy(self.source_lang_combo)
        
        target_lang_label = QLabel("目标语言:")
        self.target_lang_combo = QComboBox()
        self.target_lang_combo.setAccessibleName("目标语言")
        target_lang_label.setBuddy(self.target_lang_combo)
        
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
        self.browse_btn.setAccessibleName("浏览视频文件")
        
        self.continue_btn = QPushButton("继续")
        self.continue_btn.setIcon(self.icon_manager.get_icon("next"))
        self.continue_btn.setProperty("primary", True)
        self.continue_btn.setAccessibleName("继续处理视频")
        self.continue_btn.setEnabled(False)  # 初始禁用
        
        btn_layout.addWidget(self.browse_btn)
        btn_layout.addWidget(self.continue_btn)
        
        main_layout.addLayout(btn_layout)
    
    def setup_connections(self):
        """设置信号和槽连接"""
        self.browse_btn.clicked.connect(self.browse_video)
        self.continue_btn.clicked.connect(self.continue_signal)
        self.drop_zone.file_dropped.connect(self.set_video_path)
        self.drop_zone.browse_requested.connect(self.browse_video)
    
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
        if not os.path.isfile(filepath):
            logging.error(f"文件不存在: {filepath}")
            return

        extension = os.path.splitext(filepath)[1].lower()
        if extension not in self.drop_zone.supported_extensions:
            logging.error("不支持的视频格式: %s", extension or "无扩展名")
            return
        
        self.video_path = filepath
        self.video_info = None
        
        # 保存目录到配置
        self.config["last_directory"] = os.path.dirname(filepath)
        
        self.continue_btn.setEnabled(False)

        # 在后台加载视频信息；快速切换文件时仅接受最后一次请求。
        self.load_video_info()
        
        # 显示视频信息面板
        self.video_info_frame.setVisible(True)
        
        # 更新拖放区域
        filename = os.path.basename(filepath)
        self.drop_zone.setText(f"已选择：{filename}\n\n拖放新文件或按 Enter 可替换")
        self.drop_zone.setAccessibleDescription(
            f"当前视频文件为 {filename}。拖放新文件，或按 Enter、空格键替换"
        )
    
    def load_video_info(self) -> None:
        """Start asynchronous metadata and thumbnail loading."""

        if not self.video_path:
            return
        self._load_generation += 1
        request_id = self._load_generation
        self.filename_label.setText(os.path.basename(self.video_path))
        self.duration_label.setText("正在读取...")
        self.resolution_label.setText("正在读取...")
        self.thumbnail_label.setPixmap(QPixmap())
        self.thumbnail_label.setText("正在生成预览...")

        task = _VideoLoadTask(request_id, self.video_path, self.video_processor)
        self._active_load_tasks.add(task)
        task.signals.loaded.connect(self._video_load_finished, Qt.QueuedConnection)
        task.signals.failed.connect(self._video_load_failed, Qt.QueuedConnection)
        self._thread_pool.start(task)

    @pyqtSlot(object)
    def _video_load_finished(self, result: _VideoLoadResult) -> None:
        self._discard_load_task(result.request_id)
        if result.request_id != self._load_generation or result.video_path != self.video_path:
            return

        info = dict(result.info)
        self.video_info = info
        self.filename_label.setText(str(info.get("filename") or os.path.basename(result.video_path)))
        duration_sec = max(0.0, float(info.get("duration", 0) or 0))
        hours = int(duration_sec // 3600)
        minutes = int((duration_sec % 3600) // 60)
        seconds = int(duration_sec % 60)
        self.duration_label.setText(f"{hours:02d}:{minutes:02d}:{seconds:02d}")

        width = int(info.get("width", 0) or 0)
        height = int(info.get("height", 0) or 0)
        self.resolution_label.setText(f"{width} × {height}" if width and height else "未知")

        pixmap = QPixmap()
        if result.thumbnail_data:
            pixmap.loadFromData(result.thumbnail_data)
        if pixmap.isNull():
            self.thumbnail_label.setText("预览不可用")
        else:
            self.thumbnail_label.setPixmap(
                pixmap.scaled(
                    self.thumbnail_label.size(),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
        self.continue_btn.setEnabled(True)
        self.video_info_loaded.emit(info)

    @pyqtSlot(int, str, str)
    def _video_load_failed(
        self,
        request_id: int,
        video_path: str,
        message: str,
    ) -> None:
        self._discard_load_task(request_id)
        if request_id != self._load_generation or video_path != self.video_path:
            return
        self.video_info = None
        self.filename_label.setText(os.path.basename(video_path))
        self.duration_label.setText("未知")
        self.resolution_label.setText("未知")
        self.thumbnail_label.setText("预览不可用")
        self.continue_btn.setEnabled(False)
        self.video_info_error.emit(message)

    def _discard_load_task(self, request_id: int) -> None:
        for task in tuple(self._active_load_tasks):
            if task.request_id == request_id:
                self._active_load_tasks.discard(task)
                return

    def closeEvent(self, event) -> None:
        """Invalidate callbacks while allowing shared-pool jobs to finish safely."""

        self._load_generation += 1
        super().closeEvent(event)
    
    def get_source_language(self) -> str:
        """获取选择的源语言代码"""
        return self.source_lang_combo.currentData()
    
    def get_target_language(self) -> str:
        """获取选择的目标语言代码"""
        return self.target_lang_combo.currentData()
