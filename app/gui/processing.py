import logging
import os
import time
from typing import Any, Dict

from PyQt5.QtCore import Qt, QThread, QTimer, pyqtSignal, pyqtSlot
from PyQt5.QtGui import QColor, QIcon, QTextCursor
from PyQt5.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.gui.improved_processing import ImprovedProcessingWorker
from app.utils.logger import add_log_viewer


class ProcessingStage(QWidget):
    """处理阶段组件，显示单个处理步骤的状态"""
    
    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.title = title
        self.status = "waiting"  # 'waiting', 'processing', 'complete', 'error'
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # 标题和状态
        header_layout = QHBoxLayout()
        self.title_label = QLabel(title)
        self.title_label.setProperty("heading", True)
        self.status_label = QLabel("等待中")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.status_label.setProperty("stage", "waiting")
        
        header_layout.addWidget(self.title_label)
        header_layout.addWidget(self.status_label)
        
        layout.addLayout(header_layout)
        
        # 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)
    
    def set_status(self, status: str, progress: int = None):
        """
        设置阶段状态
        
        Args:
            status: 状态 ('waiting', 'processing', 'complete', 'error')
            progress: 进度值 (0-100)
        """
        self.status = status
        
        # 更新状态标签
        if status == "waiting":
            self.status_label.setText("等待中")
            self.status_label.setProperty("stage", "waiting")
        elif status == "processing":
            self.status_label.setText("处理中...")
            self.status_label.setProperty("stage", "processing")
        elif status == "complete":
            self.status_label.setText("完成")
            self.status_label.setProperty("stage", "complete")
        elif status == "error":
            self.status_label.setText("错误")
            self.status_label.setProperty("stage", "error")
        
        # 应用样式更改
        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)
        
        # 更新进度条
        if progress is not None:
            self.progress_bar.setValue(progress)

class ProcessingWidget(QWidget):
    """处理状态显示界面"""
    
    # 信号：当处理完成时发出
    processing_completed = pyqtSignal(dict)
    
    # 信号：当处理出错时发出
    processing_error = pyqtSignal(str)

    # 用户主动取消与失败分开，避免弹出“严重错误”。
    processing_cancelled = pyqtSignal()
    
    # 信号：日志消息，用于线程安全更新日志区域
    log_signal = pyqtSignal(str, str)  
    
    def __init__(self, config: Dict[str, Any], parent=None):
        super().__init__(parent)
        self.config = config
        self.is_processing = False
        self.start_time = 0
        self.result_data = {}
        self._thread = None
        self._worker = None
        
        self.setup_ui()
        self.setup_connections()
        
        # 使用日志查看器并连接日志信号
        self._log_viewer_handler = add_log_viewer(self.append_log)
        viewer_handler = self._log_viewer_handler

        def detach_viewer(_object=None, handler=viewer_handler):
            root_logger = logging.getLogger()
            root_logger.removeHandler(handler)
            handler.close()

        # Parent-owned widgets are often destroyed without receiving their
        # own closeEvent. Detach the root-logger callback at the QObject
        # lifetime boundary so it cannot retain or call a deleted widget.
        self.destroyed.connect(detach_viewer)
        # 线程安全将日志发射到 GUI 线程
        self.log_signal.connect(self._append_log_text)
    
    def setup_ui(self):
        """设置用户界面"""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(20)
        
        # 标题
        title_label = QLabel("正在处理视频")
        title_label.setProperty("heading", True)
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(title_label)
        
        # 状态标签
        self.status_label = QLabel("准备处理...")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(self.status_label)
        
        # 预计剩余时间
        self.time_label = QLabel("预计剩余时间: 计算中...")
        self.time_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(self.time_label)
        
        # 处理阶段
        stages_frame = QFrame()
        stages_frame.setFrameStyle(QFrame.Shape.StyledPanel | QFrame.Shadow.Raised)
        stages_layout = QVBoxLayout(stages_frame)
        
        self.extraction_stage = ProcessingStage("1. 提取音频")
        self.recognition_stage = ProcessingStage("2. 语音识别")
        self.translation_stage = ProcessingStage("3. 文本翻译")
        self.subtitle_stage = ProcessingStage("4. 字幕生成")
        
        stages_layout.addWidget(self.extraction_stage)
        stages_layout.addWidget(self.recognition_stage)
        stages_layout.addWidget(self.translation_stage)
        stages_layout.addWidget(self.subtitle_stage)
        
        main_layout.addWidget(stages_frame)
        
        # 日志区域
        log_group = QFrame()
        log_group.setFrameStyle(QFrame.Shape.StyledPanel | QFrame.Shadow.Sunken)
        log_layout = QVBoxLayout(log_group)
        
        log_header = QLabel("处理日志")
        log_header.setProperty("heading", True)
        log_layout.addWidget(log_header)
        
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setFixedHeight(150)
        log_layout.addWidget(self.log_text)
        
        main_layout.addWidget(log_group)
        
        # 按钮
        btn_layout = QHBoxLayout()
        btn_layout.addStretch(1)
        
        self.cancel_btn = QPushButton("取消")
        self.cancel_btn.setIcon(QIcon.fromTheme("process-stop"))
        
        btn_layout.addWidget(self.cancel_btn)
        
        main_layout.addLayout(btn_layout)
    
    def setup_connections(self):
        """设置信号和槽连接"""
        self.cancel_btn.clicked.connect(self.cancel_processing)
        
        # 设置定时更新
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_elapsed_time)
        self.timer.setInterval(1000)  # 每秒更新一次
    
    def start_processing(
        self,
        video_path: str,
        source_language: str,
        target_language: str,
        whisper_model: str | None = None,
        translation_provider: str | None = None,
    ):
        """
        开始处理视频
        
        Args:
            video_path: 视频文件路径
            source_language: 源语言代码
            target_language: 目标语言代码
            whisper_model: Whisper模型类型
            translation_provider: 翻译服务提供商
        """
        if self.is_processing or (
            self._thread is not None and self._thread.isRunning()
        ):
            logging.warning("已有处理任务在进行中")
            return

        getter = getattr(self.config, "get", None)

        def config_value(key, default):
            if callable(getter):
                return getter(key, default)
            return getattr(self.config, key, default)

        worker_config = {
            "whisper_model": whisper_model
            or config_value("whisper_model", "base"),
            "translation_provider": translation_provider
            or config_value("translation_provider", "openai"),
            # Copy secrets into this task snapshot. AppConfig intentionally
            # keeps them in memory only; mutating settings later cannot alter
            # a running task's provider credentials.
            "api_keys": dict(config_value("api_keys", {}) or {}),
        }
        
        self.is_processing = True
        self.start_time = time.time()
        self.timer.start()
        
        # 重置界面
        self.reset_ui()
        self.status_label.setText(f"正在处理: {os.path.basename(video_path)}")
        self.append_log(f"开始处理视频: {video_path}")
        
        # 更新阶段状态
        self.extraction_stage.set_status("waiting", 0)
        self.recognition_stage.set_status("waiting", 0)
        self.translation_stage.set_status("waiting", 0)
        self.subtitle_stage.set_status("waiting", 0)
        
        # 不在这里预加载模型，让 ImprovedProcessingWorker 处理
        # 这样避免重复加载 Whisper 模型和重复创建翻译器
        
        # 使用改进的处理工作器
        thread = QThread(self)
        worker = ImprovedProcessingWorker(
            video_path,
            source_language,
            target_language,
            worker_config,
        )
        self._thread = thread
        self._worker = worker
        worker.moveToThread(thread)
        
        # 连接信号
        thread.started.connect(worker.run)
        worker.finished.connect(self.on_processing_finished)
        worker.error.connect(self.on_processing_error)
        worker.cancelled.connect(self.on_processing_cancelled)
        worker.progress.connect(self.handle_stage_progress)
        worker.log.connect(self.append_log)
        
        # 清理连接
        worker.finished.connect(worker.deleteLater)
        worker.error.connect(worker.deleteLater)
        worker.cancelled.connect(worker.deleteLater)
        worker.finished.connect(thread.quit)
        worker.error.connect(thread.quit)
        worker.cancelled.connect(thread.quit)
        thread.finished.connect(
            lambda: self._on_thread_finished(thread, worker)
        )
        
        # 启动线程
        thread.start()
    
    def handle_stage_progress(self, stage: int, status: str, progress: int):
        if stage == 1:
            self.extraction_stage.set_status(status, progress)
        elif stage == 2:
            self.recognition_stage.set_status(status, progress)
        elif stage == 3:
            self.translation_stage.set_status(status, progress)
        elif stage == 4:
            self.subtitle_stage.set_status(status, progress)

    def on_processing_finished(self, result):
        self.timer.stop()
        self.status_label.setText("处理完成")
        self.processing_completed.emit(result)

    def on_processing_error(self, msg):
        self.timer.stop()
        self.status_label.setText("处理失败")
        self.processing_error.emit(msg)

    def on_processing_cancelled(self):
        self.timer.stop()
        self.status_label.setText("处理已取消，可稍后继续")
        self.append_log("处理已安全取消，恢复点已保留", logging.WARNING)
        self.processing_cancelled.emit()

    def _on_thread_finished(self, thread, worker):
        """在后台线程退出后安全释放 Qt 对象。"""
        if self._worker is worker:
            self._worker = None
        if self._thread is thread:
            self._thread = None
            self.is_processing = False
        thread.deleteLater()

    def cancel_processing(self):
        """取消处理过程"""
        if not self.is_processing:
            return
        
        self.append_log("用户取消处理")
        
        # 取消改进的处理器
        self.cancel_btn.setEnabled(False)
        self.status_label.setText("正在安全停止当前阶段...")
        if self._worker is not None:
            # Update the UI first: injected/test workers may emit the terminal
            # signal synchronously from cancel().
            self._worker.cancel()
        # 不强杀 QThread：底层阶段会在安全边界发出 cancelled 信号。
    
    def reset_ui(self):
        """重置界面状态"""
        self.log_text.clear()
        self.status_label.setText("准备处理...")
        self.time_label.setText("预计剩余时间: 计算中...")
        self.cancel_btn.setEnabled(True)
    
    def update_elapsed_time(self):
        """更新已用时间和预计剩余时间"""
        if not self.is_processing:
            return
        
        elapsed = time.time() - self.start_time
        elapsed_formatted = self._format_time(elapsed)
        
        # 简单估计总时间和剩余时间
        # 这里使用一个非常简单的估计方法，根据各阶段的完成情况
        total_progress = 0
        
        for stage in [self.extraction_stage, self.recognition_stage, 
                    self.translation_stage, self.subtitle_stage]:
            if stage.status == "complete":
                total_progress += 100
            elif stage.status == "processing":
                total_progress += stage.progress_bar.value()
        
        # 总进度百分比
        total_percent = total_progress / 4
        
        # 如果有进度，估计剩余时间
        if total_percent > 0:
            estimated_total = elapsed / (total_percent / 100)
            remaining = estimated_total - elapsed
            
            if remaining > 0:
                self.time_label.setText(f"已用时间: {elapsed_formatted} | "
                                      f"剩余: {self._format_time(remaining)}")
            else:
                self.time_label.setText(f"已用时间: {elapsed_formatted}")
        else:
            self.time_label.setText(f"已用时间: {elapsed_formatted}")
    
    def append_log(self, message: str, level: int = logging.INFO):
        """
        添加日志消息到日志区域
        
        Args:
            message: 日志消息
            level: 日志级别
        """
        # 根据日志级别设置颜色
        color = "#000000"  # 默认黑色
        
        if level == logging.DEBUG:
            color = "#808080"  # 灰色
        elif level == logging.WARNING:
            color = "#FF8C00"  # 深橙色
        elif level == logging.ERROR:
            color = "#FF0000"  # 红色
        elif level == logging.CRITICAL:
            color = "#8B0000"  # 深红色
        
        # 发射日志到主线程显示
        try:
            self.log_signal.emit(message, color)
        except RuntimeError:
            # A queued root-logger record may race with Qt object teardown.
            # The handler is removed on destruction; silently discard the
            # last record instead of recursively emitting a logging error.
            pass

    def closeEvent(self, event):
        self._remove_log_viewer()
        super().closeEvent(event)

    def _remove_log_viewer(self):
        handler = getattr(self, "_log_viewer_handler", None)
        if handler is None:
            return
        logging.getLogger().removeHandler(handler)
        handler.close()
        self._log_viewer_handler = None
    
    @pyqtSlot(str, str)
    def _append_log_text(self, message: str, color: str):
        """
        实际添加文本到日志区域的方法（在GUI线程中调用）
        
        Args:
            message: 日志消息
            color: 文本颜色
        """
        cursor = self.log_text.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        
        format = cursor.charFormat()
        format.setForeground(QColor(color))
        cursor.setCharFormat(format)
        
        cursor.insertText(message + "\n")
        
        # 自动滚动
        self.log_text.setTextCursor(cursor)
        self.log_text.ensureCursorVisible()
    
    @staticmethod
    def _format_time(seconds: float) -> str:
        """格式化时间（秒）为人类可读形式"""
        if seconds < 60:
            return f"{seconds:.1f}秒"
        elif seconds < 3600:
            minutes = int(seconds // 60)
            sec = int(seconds % 60)
            return f"{minutes}分{sec}秒"
        else:
            hours = int(seconds // 3600)
            minutes = int((seconds % 3600) // 60)
            return f"{hours}小时{minutes}分"
