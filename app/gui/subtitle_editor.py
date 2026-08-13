#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Subtitle Editor GUI module for video translation system.
Provides interface for editing subtitles with video preview.
"""

import copy
import importlib
import logging
import os
import shutil
import subprocess
import sys
import tempfile
from typing import List

from PyQt5.QtCore import (
    QEvent,
    QObject,
    QRunnable,
    Qt,
    QThreadPool,
    QTimer,
    pyqtSignal,
    pyqtSlot,
)
from PyQt5.QtGui import (
    QColor,
    QKeySequence,
    QPixmap,
)
from PyQt5.QtMultimedia import QMediaPlayer
from PyQt5.QtMultimediaWidgets import QVideoWidget
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QColorDialog,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QShortcut,
    QSizePolicy,
    QSlider,
    QSpinBox,
    QSplitter,
    QStackedWidget,
    QTextEdit,
    QToolBar,
    QUndoCommand,
    QUndoStack,
    QVBoxLayout,
    QWidget,
)

from app.core.subtitle import SubtitleProcessor, SubtitleSegment
from app.gui.custom_widgets import TimelineWidget
from app.utils.format_converter import format_time

logger = logging.getLogger(__name__)

# VLC is an optional playback helper. Importing it can fail with an OSError
# when the Python module exists but its native library does not, so keep the
# import lazy and guarded. The editor remains usable for subtitle work and
# falls back to an asynchronous static FFmpeg frame without VLC.
vlc = None
vlc_available = False
_vlc_import_checked = False
_vlc_import_error = None
# Retained as a compatibility/introspection marker for older integrations.
# OpenCV is no longer a preview backend; static fallback is handled by FFmpeg.
_cv2_import_checked = False

# Add VLC DLL search path on Windows immediately before the optional import.
libvlc_path = None
plugins_path = None


def _configure_windows_vlc_paths():
    """配置 Windows VLC 原生库搜索路径。"""
    global libvlc_path, plugins_path
    if not sys.platform.startswith("win"):
        return

    vlc_paths = [
        os.environ.get("VLC_DIR"),
        r"C:\Program Files\VideoLAN\VLC",
        r"C:\Program Files (x86)\VideoLAN\VLC"
    ]

    for path in vlc_paths:
        if path and os.path.isdir(path):
            if hasattr(os, "add_dll_directory"):
                os.add_dll_directory(path)
            if path not in os.environ.get('PATH', ''):
                os.environ['PATH'] = path + os.pathsep + os.environ.get('PATH', '')
            libvlc_path = path
            plugins_path = os.path.join(path, 'plugins')
            logger.info(f"已添加VLC目录: {path}")
            break


def _load_vlc_module():
    """延迟加载 python-vlc；缺失模块或原生库时返回 None。"""
    global vlc, _vlc_import_checked, _vlc_import_error
    if _vlc_import_checked:
        return vlc

    _vlc_import_checked = True
    _configure_windows_vlc_paths()
    try:
        vlc = importlib.import_module("vlc")
    except (ImportError, OSError) as exc:
        _vlc_import_error = exc
        vlc = None
        logger.info("VLC 播放后端不可用，将使用静态画面预览: %s", exc)
    return vlc


# 检查 VLC 是否可用的函数
def is_vlc_available():
    """检查 VLC 库是否可用"""
    global vlc_available
    vlc_module = _load_vlc_module()
    if vlc_module is None:
        vlc_available = False
        return False

    test_instance = None
    test_player = None
    try:
        # 尝试创建一个简单的 VLC 实例
        test_instance = vlc_module.Instance(['--quiet'])
        if test_instance is None:
            vlc_available = False
            return False
        # 检查是否可以创建媒体播放器
        test_player = test_instance.media_player_new()
        if test_player is None:
            vlc_available = False
            return False
        vlc_available = True
        return True
    except Exception as e:
        vlc_available = False
        logger.info(f"VLC 不可用，将使用静态画面预览: {str(e)}")
        return False
    finally:
        try:
            if test_player is not None and hasattr(test_player, "release"):
                test_player.release()
            if test_instance is not None and hasattr(test_instance, "release"):
                test_instance.release()
        except Exception:
            logger.debug("释放 VLC 可用性检查资源时出错", exc_info=True)


class _FrameExtractionSignals(QObject):
    """Thread-safe result channel for one static-preview request."""

    succeeded = pyqtSignal(int, str, bytes)
    failed = pyqtSignal(int, str, str)


class _FrameExtractionTask(QRunnable):
    """Extract one preview frame without blocking the Qt GUI thread."""

    def __init__(self, request_id: int, video_path: str, ffmpeg_path: str = "ffmpeg"):
        super().__init__()
        self.request_id = request_id
        self.video_path = video_path
        self.ffmpeg_path = ffmpeg_path
        self.signals = _FrameExtractionSignals()

    @pyqtSlot()
    def run(self):
        file_descriptor, frame_path = tempfile.mkstemp(
            prefix="video-translator-frame-", suffix=".jpg"
        )
        os.close(file_descriptor)
        try:
            subprocess.run(
                [
                    self.ffmpeg_path,
                    "-y",
                    "-ss",
                    "00:00:00",
                    "-i",
                    self.video_path,
                    "-frames:v",
                    "1",
                    frame_path,
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=True,
                timeout=30,
            )
            with open(frame_path, "rb") as frame_file:
                frame_data = frame_file.read()
            if not frame_data:
                raise ValueError("首帧图像为空")
            self.signals.succeeded.emit(
                self.request_id, self.video_path, frame_data
            )
        except Exception as exc:
            self.signals.failed.emit(
                self.request_id, self.video_path, str(exc)
            )
        finally:
            try:
                os.unlink(frame_path)
            except FileNotFoundError:
                pass


class SubtitleListItem(QListWidgetItem):
    """表示单个字幕片段的列表项。"""
    
    def __init__(self, segment: SubtitleSegment, index: int):
        super().__init__()
        self.segment = segment
        self.index = index
        self.update_display()
        
    def update_display(self):
        """根据字幕数据更新显示文本。"""
        start_time = format_time(self.segment.start_time)
        end_time = format_time(self.segment.end_time)
        
        # Truncate text for display if too long
        orig_text = self.segment.original_text
        if len(orig_text) > 40:
            orig_text = orig_text[:37] + "..."
        
        display_text = f"{self.index}. [{start_time} - {end_time}] {orig_text}"
        self.setText(display_text)


class _SubtitleStateCommand(QUndoCommand):
    """Restore an editor-wide subtitle state for undo and redo.

    Mutating slots update the live state before pushing a command.  Skipping
    the first ``redo`` is important for text edits: rebuilding the editor on
    every keystroke would reset the cursor and break normal typing.
    """

    _MERGE_ID = 0x5654

    def __init__(
        self,
        editor,
        text: str,
        before_segments,
        after_segments,
        before_selection,
        after_selection,
        merge_key=None,
    ):
        super().__init__(text)
        self._editor = editor
        self._before_segments = before_segments
        self._after_segments = after_segments
        self._before_selection = before_selection
        self._after_selection = after_selection
        self._merge_key = merge_key
        self._first_redo = True

    def id(self):
        """Allow adjacent changes in one typing/timing session to coalesce."""
        return self._MERGE_ID if self._merge_key is not None else -1

    def mergeWith(self, other):
        if not isinstance(other, _SubtitleStateCommand):
            return False
        if self._editor is not other._editor or self._merge_key != other._merge_key:
            return False
        self._after_segments = other._after_segments
        self._after_selection = other._after_selection
        return True

    def undo(self):
        self._editor._restore_history_state(
            self._before_segments, self._before_selection
        )

    def redo(self):
        if self._first_redo:
            self._first_redo = False
            self._editor._finish_live_history_change()
            return
        self._editor._restore_history_state(
            self._after_segments, self._after_selection
        )


class SubtitleValidationDialog(QDialog):
    """Display validation findings and let users jump to a segment."""

    issueActivated = pyqtSignal(int)

    _MESSAGES = {
        "no_segments": "没有可检查的字幕片段",
        "non_finite_timing": "开始或结束时间不是有效数字",
        "negative_start": "开始时间不能为负数",
        "invalid_range": "结束时间必须晚于开始时间",
        "overlap": "与前一个字幕片段重叠",
        "very_short": "显示时间短于 0.5 秒",
        "very_long": "显示时间长于 7 秒",
        "empty_text": "原文和译文均为空",
    }

    def __init__(self, issues: List[dict], parent=None):
        super().__init__(parent)
        self.issues = issues
        self.setWindowTitle("字幕检查结果")
        self.setMinimumSize(560, 340)
        self.setAccessibleName("字幕检查结果")

        layout = QVBoxLayout(self)
        error_count = sum(issue.get("type") == "error" for issue in issues)
        warning_count = sum(issue.get("type") == "warning" for issue in issues)
        self.summary_label = QLabel(
            f"共发现 {len(issues)} 个问题：{error_count} 个错误，"
            f"{warning_count} 个警告"
        )
        self.summary_label.setProperty("heading", True)
        self.summary_label.setAccessibleName("字幕问题汇总")
        layout.addWidget(self.summary_label)

        hint = QLabel("选择问题并点击“转到字幕”，或双击列表项。")
        hint.setProperty("muted", True)
        layout.addWidget(hint)

        self.issue_list = QListWidget()
        self.issue_list.setAccessibleName("字幕问题列表")
        self.issue_list.setAlternatingRowColors(True)
        for issue in issues:
            severity = "错误" if issue.get("type") == "error" else "警告"
            segment_idx = issue.get("segment_idx")
            location = f"第 {segment_idx + 1} 段" if segment_idx is not None else "全局"
            message = self._MESSAGES.get(
                issue.get("code"), issue.get("message", "未知问题")
            )
            item = QListWidgetItem(f"[{severity}] {location} · {message}")
            item.setData(Qt.UserRole, segment_idx)
            item.setToolTip(issue.get("message", message))
            self.issue_list.addItem(item)
        layout.addWidget(self.issue_list, 1)

        self.button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        self.jump_button = self.button_box.addButton(
            "转到字幕", QDialogButtonBox.ButtonRole.ActionRole
        )
        self.jump_button.setAccessibleName("转到有问题的字幕片段")
        self.jump_button.clicked.connect(self._activate_current)
        self.button_box.rejected.connect(self.reject)
        layout.addWidget(self.button_box)

        self.issue_list.currentItemChanged.connect(self._update_jump_button)
        self.issue_list.itemDoubleClicked.connect(lambda _item: self._activate_current())
        if self.issue_list.count():
            self.issue_list.setCurrentRow(0)
        self._update_jump_button(self.issue_list.currentItem())

    def _update_jump_button(self, item, _previous=None):
        self.jump_button.setEnabled(
            item is not None and item.data(Qt.UserRole) is not None
        )

    def _activate_current(self):
        item = self.issue_list.currentItem()
        if item is None:
            return
        segment_idx = item.data(Qt.UserRole)
        if segment_idx is None:
            return
        self.issueActivated.emit(int(segment_idx))
        self.accept()


class SegmentEditDialog(QDialog):
    """用于精细编辑单个字幕片段的对话框。"""
    
    def __init__(self, segment: SubtitleSegment, parent=None):
        super().__init__(parent)
        self.segment = segment
        self.setWindowTitle("编辑字幕片段")
        self.setup_ui()
        
    def setup_ui(self):
        """Set up the dialog UI components"""
        layout = QGridLayout(self)
        
        # Time controls
        time_group = QGroupBox("时间")
        time_layout = QGridLayout()
        
        # Start time
        time_layout.addWidget(QLabel("开始时间："), 0, 0)
        self.start_time = QDoubleSpinBox()
        self.start_time.setDecimals(3)
        self.start_time.setRange(0, 86400)  # 24 hours max
        self.start_time.setValue(self.segment.start_time)
        self.start_time.setSingleStep(0.1)
        time_layout.addWidget(self.start_time, 0, 1)
        
        # End time
        time_layout.addWidget(QLabel("结束时间："), 1, 0)
        self.end_time = QDoubleSpinBox()
        self.end_time.setDecimals(3)
        self.end_time.setRange(0, 86400)  # 24 hours max
        self.end_time.setValue(self.segment.end_time)
        self.end_time.setSingleStep(0.1)
        time_layout.addWidget(self.end_time, 1, 1)
        
        # Duration (calculated)
        time_layout.addWidget(QLabel("持续时间："), 2, 0)
        self.duration = QLabel(f"{self.segment.end_time - self.segment.start_time:.3f} 秒")
        time_layout.addWidget(self.duration, 2, 1)
        
        # Connect signals to update duration
        self.start_time.valueChanged.connect(self.update_duration)
        self.end_time.valueChanged.connect(self.update_duration)
        
        time_group.setLayout(time_layout)
        layout.addWidget(time_group, 0, 0, 1, 2)
        
        # Text editing
        text_group = QGroupBox("文本")
        text_layout = QVBoxLayout()
        
        # Original text
        text_layout.addWidget(QLabel("原文："))
        self.original_text = QTextEdit()
        self.original_text.setPlainText(self.segment.original_text)
        text_layout.addWidget(self.original_text)
        
        # Translated text
        text_layout.addWidget(QLabel("译文："))
        self.translated_text = QTextEdit()
        self.translated_text.setPlainText(self.segment.translated_text)
        text_layout.addWidget(self.translated_text)
        
        text_group.setLayout(text_layout)
        layout.addWidget(text_group, 1, 0, 1, 2)
        
        # Style options
        style_group = QGroupBox("样式（高级）")
        style_layout = QGridLayout()
        
        # Font size
        style_layout.addWidget(QLabel("字号："), 0, 0)
        self.font_size = QSpinBox()
        self.font_size.setRange(8, 72)
        
        # Set initial value from segment style or default
        if self.segment.style and 'fontsize' in self.segment.style:
            self.font_size.setValue(int(self.segment.style['fontsize']))
        else:
            self.font_size.setValue(24)  # Default font size
            
        style_layout.addWidget(self.font_size, 0, 1)
        
        # Text color
        style_layout.addWidget(QLabel("文字颜色："), 1, 0)
        self.color_button = QPushButton()
        self.current_color = QColor("white")  # Default
        
        # Set initial color from segment style or default
        if self.segment.style and 'primarycolour' in self.segment.style:
            color_str = self.segment.style['primarycolour']
            if color_str.startswith('&H'):  # ASS color format
                # Convert ASS color to RGB (ASS uses BBGGRR format after &H)
                # This is a simplified conversion, might need adjustment
                color_hex = color_str[2:]
                if len(color_hex) >= 6:
                    b = int(color_hex[0:2], 16)
                    g = int(color_hex[2:4], 16)
                    r = int(color_hex[4:6], 16)
                    self.current_color = QColor(r, g, b)
            else:
                self.current_color = QColor(color_str)
        
        self.update_color_button()
        self.color_button.clicked.connect(self.select_color)
        style_layout.addWidget(self.color_button, 1, 1)
        
        style_group.setLayout(style_layout)
        layout.addWidget(style_group, 2, 0, 1, 2)
        
        # Dialog buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box, 3, 0, 1, 2)
        
        # Set dialog size
        self.resize(500, 600)
    
    def update_color_button(self):
        """Update the color button's background to show the selected color"""
        style = f"background-color: {self.current_color.name()};"
        self.color_button.setStyleSheet(style)
        self.color_button.setText(self.current_color.name())
        
        # Use white or black text depending on color brightness
        if self.current_color.lightnessF() > 0.5:
            self.color_button.setStyleSheet(style + "color: black;")
        else:
            self.color_button.setStyleSheet(style + "color: white;")
    
    def select_color(self):
        """Open color picker dialog"""
        color = QColorDialog.getColor(self.current_color, self, "选择文字颜色")
        if color.isValid():
            self.current_color = color
            self.update_color_button()
    
    def update_duration(self):
        """Update the duration label when start or end time changes"""
        start = self.start_time.value()
        end = self.end_time.value()
        
        # Ensure end time is not before start time
        if end < start:
            self.end_time.setValue(start)
            end = start
            
        duration = end - start
        self.duration.setText(f"{duration:.3f} 秒")
    
    def accept(self):
        """Apply changes to the segment when OK is clicked"""
        # Update segment data
        self.segment.start_time = self.start_time.value()
        self.segment.end_time = self.end_time.value()
        self.segment.original_text = self.original_text.toPlainText()
        self.segment.translated_text = self.translated_text.toPlainText()
        
        # Update style
        if self.segment.style is None:
            self.segment.style = {}
            
        self.segment.style['fontsize'] = str(self.font_size.value())
        
        # Convert RGB color to ASS color format (&HBBGGRR)
        r, g, b = self.current_color.red(), self.current_color.green(), self.current_color.blue()
        ass_color = f"&H{b:02X}{g:02X}{r:02X}"
        self.segment.style['primarycolour'] = ass_color
        
        super().accept()


class SubtitleEditor(QWidget):
    """
    Main subtitle editor widget that provides an interface for
    editing subtitle segments with video preview.
    """
    
    # Signals
    segmentsChanged = pyqtSignal()  # Emitted when subtitle data changes
    videoPositionChanged = pyqtSignal(float)  # Current video position in seconds
    playStateChanged = pyqtSignal(bool)  # True when playing, False when paused
    importSubtitleRequested = pyqtSignal()
    
    def __init__(self, video_path: str, subtitle_processor: SubtitleProcessor, parent=None):
        """
        Initialize the subtitle editor.
        
        Args:
            video_path: Path to the video file
            subtitle_processor: Instance of SubtitleProcessor with loaded segments
            parent: Parent widget
        """
        super().__init__(parent)
        self.video_path = video_path
        self.subtitle_processor = subtitle_processor
        self.segments = subtitle_processor.segments
        self.current_segment_index = -1  # No segment selected initially
        self.current_position = 0.0  # Current video position in seconds
        self.is_playing = False
        self.undo_stack = QUndoStack(self)
        self._history_restoring = False
        self._edit_session = 0
        self._last_history_state = self._snapshot_segments()
        self._fallback_generation = 0
        self._fallback_tasks = {}
        self._fallback_source_pixmap = QPixmap()
        self._fallback_thread_pool = QThreadPool.globalInstance()
        self._is_closing = False
        self._playback_prepare_timer = QTimer(self)
        self._playback_prepare_timer.setSingleShot(True)
        self._playback_prepare_timer.timeout.connect(self._run_scheduled_playback_prepare)
        self._scheduled_project_import = False
        self._vlc_init_timer = QTimer(self)
        self._vlc_init_timer.setSingleShot(True)
        self._vlc_init_timer.timeout.connect(self._run_scheduled_vlc_init)
        
        # Ensure media_player attribute exists for seek_to_position
        self.media_player = None
        
        # Subtitle display options
        self.show_original = True
        self.show_translation = True
        
        # Playback backend: only use VLC for audio/video
        self.vlc_instance = None
        self.vlc_player = None
        self.vlc_timer = None
        self.use_vlc_playback = False
        
        # Initialize UI
        self.init_ui()

        # Set up timer for subtitle display updates
        self.subtitle_timer = QTimer(self)
        self.subtitle_timer.setInterval(100)  # Check subtitle display every 100ms
        self.subtitle_timer.timeout.connect(self.update_subtitle_display)
        self.subtitle_timer.start()

    def _snapshot_segments(self):
        """Return a detached copy suitable for a history command."""
        return copy.deepcopy(self.segments)

    @staticmethod
    def _selection_for_state(selection, segment_count):
        if not segment_count:
            return -1
        return min(max(int(selection), 0), segment_count - 1)

    def _sync_processor_segments(self):
        """Keep the processor, editor, timeline, and exporter on one list."""
        self.subtitle_processor.segments = self.segments

    def _finish_live_history_change(self):
        """Record the new baseline after the initial command push."""
        self._last_history_state = self._snapshot_segments()

    def _push_history_change(
        self,
        text,
        before_segments,
        before_selection,
        after_selection=None,
        merge_key=None,
    ):
        """Push one already-applied model change onto the shared undo stack."""
        if self._history_restoring:
            return
        after_segments = self._snapshot_segments()
        if before_segments == after_segments:
            return
        if after_selection is None:
            after_selection = self.current_segment_index
        self.undo_stack.push(
            _SubtitleStateCommand(
                self,
                text,
                before_segments,
                after_segments,
                before_selection,
                after_selection,
                merge_key,
            )
        )

    def _restore_history_state(self, segments, selection):
        """Atomically restore model and every subtitle view for undo/redo."""
        self._history_restoring = True
        try:
            self.segments = copy.deepcopy(segments)
            for index, segment in enumerate(self.segments, 1):
                segment.index = index
            self._sync_processor_segments()
            self.populate_segment_list()
            row = self._selection_for_state(selection, len(self.segments))
            if row >= 0:
                self.segment_list.setCurrentRow(row)
            else:
                self.select_segment(-1)
            self._last_history_state = self._snapshot_segments()
        finally:
            self._history_restoring = False
        self.segmentsChanged.emit()

    def clear_undo_history(self):
        """Start a clean history baseline after loading another project/video."""
        self.undo_stack.clear()
        self._last_history_state = self._snapshot_segments()
    
    def init_ui(self):
        """Initialize the user interface components"""
        # Main layout
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(2)
        
        # Toolbar with common actions
        self.create_toolbar()
        main_layout.addWidget(self.toolbar)
        
        # Main content splitter (video/preview vs editing panel)
        self.main_splitter = QSplitter(Qt.Orientation.Vertical)
        
        # Upper area: Video preview and timeline
        self.upper_container = QWidget()
        upper_layout = QVBoxLayout(self.upper_container)
        upper_layout.setContentsMargins(0, 0, 0, 0)
        
        # Video preview area
        self.video_container = QWidget()
        video_layout = QVBoxLayout(self.video_container)
        video_layout.setContentsMargins(0, 0, 0, 0)
        
        # Create video and fallback in stacked widget for proper overlay
        self.video_widget = QVideoWidget()
        # Enable native window handle for VLC embedding
        self.video_widget.setAttribute(Qt.WA_NativeWindow)
        self.video_widget.setAttribute(Qt.WA_DontCreateNativeAncestors)
        self.video_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.video_widget.setAccessibleName("视频预览")
        # Removed minimum height to allow more space for video
        self.fallback_image_label = QLabel()
        self.fallback_image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.fallback_image_label.setVisible(False)
        self.fallback_image_label.setScaledContents(False)
        self.fallback_image_label.setAccessibleName("视频静态预览")
        # Stacked widget for video and fallback
        self.video_stack = QStackedWidget()
        self.video_stack.addWidget(self.video_widget)
        self.video_stack.addWidget(self.fallback_image_label)
        self.video_stack.currentChanged.connect(
            lambda _index: self.subtitle_overlay_layer.raise_()
            if hasattr(self, "subtitle_overlay_layer")
            else None
        )
        # Allow the preview to expand naturally. A fixed width-derived height
        # made short laptop windows unusable when the editor panel also needed
        # space.
        self.video_stack.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        # Current subtitle display is a real child overlay of video_stack,
        # rather than a separate row that changes the video's layout.
        video_layout.addWidget(self.video_stack, 1)
        self.video_stack.installEventFilter(self)
        self.subtitle_overlay_layer = QWidget(self.video_stack)
        self.subtitle_overlay_layer.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.subtitle_overlay_layer.setAccessibleName("字幕预览覆盖层")
        subtitle_overlay_layout = QVBoxLayout(self.subtitle_overlay_layer)
        subtitle_overlay_layout.setContentsMargins(24, 12, 24, 20)
        subtitle_overlay_layout.addStretch(1)
        self.subtitle_display = QLabel()
        self.subtitle_display.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.subtitle_display.setStyleSheet(
            "background-color: rgba(0, 0, 0, 100);"
            "color: white;"
            "padding: 8px;"
            "border-radius: 4px;"
        )
        self.subtitle_display.setWordWrap(True)
        self.subtitle_display.setAccessibleName("当前字幕预览")
        self.subtitle_display.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.subtitle_display.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum
        )
        self.subtitle_display.setVisible(False)
        subtitle_overlay_layout.addWidget(self.subtitle_display)
        self.subtitle_overlay_layer.raise_()
        QTimer.singleShot(0, self._position_subtitle_overlay)
        
        # Video controls
        self.create_video_controls()
        video_layout.addWidget(self.video_controls)
        
        upper_layout.addWidget(self.video_container)
        
        # Timeline widget for visualizing subtitle positioning
        self.timeline = TimelineWidget(self)
        self.timeline.positionChanged.connect(self.seek_to_position)
        self.timeline.segmentSelected.connect(self.select_segment_by_index)
        upper_layout.addWidget(self.timeline)
        
        # Add to main splitter
        self.main_splitter.addWidget(self.upper_container)
        
        # Lower area: Subtitle editing
        self.editing_container = QSplitter(Qt.Orientation.Horizontal)
        
        # Left side: Segment list
        self.segment_list_container = QWidget()
        segment_list_layout = QVBoxLayout(self.segment_list_container)
        
        segment_list_header = QLabel("字幕片段")
        segment_list_header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        segment_list_layout.addWidget(segment_list_header)
        
        self.segment_list = QListWidget()
        self.segment_list.setAlternatingRowColors(True)
        self.segment_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.segment_list.setAccessibleName("字幕片段列表")
        self.segment_list.setToolTip("可使用 Ctrl/⌘ 或 Shift 连续多选片段后合并")
        self.segment_list.currentRowChanged.connect(self.select_segment)
        self.segment_list.itemDoubleClicked.connect(self.edit_segment)
        segment_list_layout.addWidget(self.segment_list)
        
        # Segment list control buttons
        segment_btn_layout = QHBoxLayout()
        
        self.add_segment_btn = QPushButton("添加")
        self.add_segment_btn.setAccessibleName("添加字幕片段")
        self.add_segment_btn.setToolTip("在当前播放位置附近添加字幕片段")
        self.add_segment_btn.clicked.connect(self.add_segment)
        segment_btn_layout.addWidget(self.add_segment_btn)
        
        self.remove_segment_btn = QPushButton("删除")
        self.remove_segment_btn.setAccessibleName("删除字幕片段")
        self.remove_segment_btn.setToolTip("删除当前字幕片段")
        self.remove_segment_btn.clicked.connect(self.remove_segment)
        segment_btn_layout.addWidget(self.remove_segment_btn)
        
        self.merge_segments_btn = QPushButton("合并")
        self.merge_segments_btn.setAccessibleName("合并字幕片段")
        self.merge_segments_btn.setToolTip("合并两个或多个连续选中的字幕片段")
        self.merge_segments_btn.clicked.connect(self.merge_segments)
        segment_btn_layout.addWidget(self.merge_segments_btn)
        
        self.split_segment_btn = QPushButton("拆分")
        self.split_segment_btn.setAccessibleName("拆分字幕片段")
        self.split_segment_btn.setToolTip("在当前播放位置拆分字幕片段（Ctrl+Shift+K）")
        self.split_segment_btn.clicked.connect(self.split_segment)
        segment_btn_layout.addWidget(self.split_segment_btn)
        
        segment_list_layout.addLayout(segment_btn_layout)
        
        # Add to editing container
        self.editing_container.addWidget(self.segment_list_container)
        
        # Right side: Text editor
        self.editor_container = QWidget()
        editor_layout = QVBoxLayout(self.editor_container)
        
        # Editor header with timing controls
        timing_layout = QGridLayout()
        
        timing_layout.addWidget(QLabel("开始时间："), 0, 0)
        self.start_time_edit = QDoubleSpinBox()
        self.start_time_edit.setDecimals(3)
        self.start_time_edit.setRange(0, 86400)  # 24 hours max
        self.start_time_edit.setSingleStep(0.1)
        self.start_time_edit.setAccessibleName("字幕开始时间")
        self.start_time_edit.setToolTip("以秒为单位，精确到毫秒")
        self.start_time_edit.valueChanged.connect(self.update_segment_timing)
        timing_layout.addWidget(self.start_time_edit, 0, 1)
        
        timing_layout.addWidget(QLabel("结束时间："), 0, 2)
        self.end_time_edit = QDoubleSpinBox()
        self.end_time_edit.setDecimals(3)
        self.end_time_edit.setRange(0, 86400)  # 24 hours max
        self.end_time_edit.setSingleStep(0.1)
        self.end_time_edit.setAccessibleName("字幕结束时间")
        self.end_time_edit.setToolTip("以秒为单位，不能早于开始时间")
        self.end_time_edit.valueChanged.connect(self.update_segment_timing)
        timing_layout.addWidget(self.end_time_edit, 0, 3)
        
        timing_layout.addWidget(QLabel("持续时间："), 0, 4)
        self.duration_label = QLabel("0.000 秒")
        timing_layout.addWidget(self.duration_label, 0, 5)
        
        editor_layout.addLayout(timing_layout)
        
        # Text editors
        text_splitter = QSplitter(Qt.Orientation.Vertical)
        
        # Original text
        original_container = QWidget()
        original_layout = QVBoxLayout(original_container)
        original_layout.setContentsMargins(0, 0, 0, 0)
        
        original_header = QLabel("原文：")
        original_layout.addWidget(original_header)
        
        self.original_text_edit = QTextEdit()
        self.original_text_edit.setAccessibleName("字幕原文")
        self.original_text_edit.document().setUndoRedoEnabled(False)
        self.original_text_edit.installEventFilter(self)
        self.original_text_edit.textChanged.connect(self.update_segment_original_text)
        original_layout.addWidget(self.original_text_edit)
        
        text_splitter.addWidget(original_container)
        
        # Translated text
        translation_container = QWidget()
        translation_layout = QVBoxLayout(translation_container)
        translation_layout.setContentsMargins(0, 0, 0, 0)
        
        translation_header = QLabel("译文：")
        translation_layout.addWidget(translation_header)
        
        self.translation_text_edit = QTextEdit()
        self.translation_text_edit.setAccessibleName("字幕译文")
        self.translation_text_edit.document().setUndoRedoEnabled(False)
        self.translation_text_edit.installEventFilter(self)
        self.translation_text_edit.textChanged.connect(self.update_segment_translation)
        translation_layout.addWidget(self.translation_text_edit)
        
        text_splitter.addWidget(translation_container)
        
        # Add to editor container
        editor_layout.addWidget(text_splitter, 1)
        
        # Add to editing container
        self.editing_container.addWidget(self.editor_container)
        
        # Set initial size ratio (33% list, 67% editor)
        self.editing_container.setSizes([100, 200])
        
        # Add to main splitter
        self.main_splitter.addWidget(self.editing_container)
        
        # Set initial size ratio (more space for video preview)
        self.main_splitter.setSizes([800, 300])
        # 设置拉伸比：视频区占3份，编辑区占1份
        self.main_splitter.setStretchFactor(0, 4)
        self.main_splitter.setStretchFactor(1, 1)
        
        # Ensure upper container expands for larger video area
        self.upper_container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        # Add main splitter to layout
        main_layout.addWidget(self.main_splitter, 1)
        
        # Status bar
        self.status_bar = QLabel("就绪")
        self.status_bar.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.status_bar.setAccessibleName("字幕编辑状态")
        self.status_bar.setStyleSheet("padding: 2px;")
        main_layout.addWidget(self.status_bar)
        
        # Load segments into UI
        self.populate_segment_list()
        
        # Set keyboard shortcuts
        self.setup_shortcuts()

    def eventFilter(self, watched, event):
        """Use focus boundaries to delimit otherwise continuous edit commands."""
        if (
            watched is getattr(self, "video_stack", None)
            and event.type() == QEvent.Type.Resize
        ):
            self._position_subtitle_overlay()
        if event.type() == QEvent.Type.FocusIn and watched in {
            self.original_text_edit,
            self.translation_text_edit,
        }:
            self._edit_session += 1
        return super().eventFilter(watched, event)

    def _position_subtitle_overlay(self):
        """Keep the mouse-transparent subtitle layer inside safe video margins."""
        if not hasattr(self, "subtitle_overlay_layer"):
            return
        self.subtitle_overlay_layer.setGeometry(self.video_stack.rect())
        self.subtitle_overlay_layer.raise_()
    
    def create_toolbar(self):
        """Create the toolbar with common actions"""
        self.toolbar = QToolBar()
        self.toolbar.setMovable(False)
        self.toolbar.setAccessibleName("字幕编辑工具栏")

        self.import_subtitle_action = self.toolbar.addAction("导入字幕")
        self.import_subtitle_action.setToolTip(
            "导入 SRT、VTT、ASS/SSA、SUB 或 SBV 字幕（Ctrl+I）"
        )
        self.import_subtitle_action.triggered.connect(
            lambda _checked=False: self.importSubtitleRequested.emit()
        )

        self.toolbar.addSeparator()
        
        # Playback controls
        self.play_action = self.toolbar.addAction("播放")
        self.play_action.setToolTip("播放或暂停视频（空格键）")
        self.play_action.triggered.connect(self.toggle_play)
        
        self.toolbar.addSeparator()
        
        # Add timing adjustment buttons
        start_back_action = self.toolbar.addAction("起点 −0.1s")
        start_back_action.setToolTip("将当前字幕的开始时间提前 0.1 秒")
        start_back_action.triggered.connect(
            lambda: self.adjust_current_segment_timing(-0.1, 0)
        )
        start_forward_action = self.toolbar.addAction("起点 +0.1s")
        start_forward_action.setToolTip("将当前字幕的开始时间延后 0.1 秒")
        start_forward_action.triggered.connect(
            lambda: self.adjust_current_segment_timing(0.1, 0)
        )
        self.toolbar.addSeparator()
        end_back_action = self.toolbar.addAction("终点 −0.1s")
        end_back_action.setToolTip("将当前字幕的结束时间提前 0.1 秒")
        end_back_action.triggered.connect(
            lambda: self.adjust_current_segment_timing(0, -0.1)
        )
        end_forward_action = self.toolbar.addAction("终点 +0.1s")
        end_forward_action.setToolTip("将当前字幕的结束时间延后 0.1 秒")
        end_forward_action.triggered.connect(
            lambda: self.adjust_current_segment_timing(0, 0.1)
        )
        
        self.toolbar.addSeparator()
        
        # View options
        self.show_original_action = self.toolbar.addAction("显示原文")
        self.show_original_action.setCheckable(True)
        self.show_original_action.setChecked(True)
        self.show_original_action.toggled.connect(self.toggle_original_display)
        
        self.show_translation_action = self.toolbar.addAction("显示译文")
        self.show_translation_action.setCheckable(True)
        self.show_translation_action.setChecked(True)
        self.show_translation_action.toggled.connect(self.toggle_translation_display)
        
        self.toolbar.addSeparator()
        
        # Validate action
        self.validate_action = self.toolbar.addAction("检查字幕")
        self.validate_action.setToolTip("检查时间重叠、时长和空文本等问题")
        self.validate_action.triggered.connect(self.validate_subtitles)
    
    def create_video_controls(self):
        """Create video playback controls"""
        self.video_controls = QWidget()
        controls_layout = QHBoxLayout(self.video_controls)
        controls_layout.setContentsMargins(0, 0, 0, 0)
        
        # Skip back 1s button
        self.back_button = QPushButton("⏪ 1s")
        self.back_button.setAccessibleName("后退一秒")
        self.back_button.setToolTip("后退 1 秒（左方向键）")
        self.back_button.clicked.connect(lambda: self.seek_relative(-1.0))
        controls_layout.addWidget(self.back_button)
        # Play/pause button
        self.play_button = QPushButton("▶")
        self.play_button.setAccessibleName("播放或暂停")
        self.play_button.setToolTip("播放或暂停视频（空格键）")
        self.play_button.clicked.connect(self.toggle_play)
        controls_layout.addWidget(self.play_button)
        # Skip forward 1s button
        self.forward_button = QPushButton("1s ⏩")
        self.forward_button.setAccessibleName("前进一秒")
        self.forward_button.setToolTip("前进 1 秒（右方向键）")
        self.forward_button.clicked.connect(lambda: self.seek_relative(1.0))
        controls_layout.addWidget(self.forward_button)

        # Position slider (full width)
        self.position_slider = QSlider(Qt.Orientation.Horizontal)
        self.position_slider.setRange(0, 1000)
        self.position_slider.setAccessibleName("视频播放位置")
        self.position_slider.setToolTip("拖动以定位视频播放时间")
        # Track slider events: press/move/release for smooth seeking
        self.position_slider.sliderPressed.connect(self._on_slider_pressed)
        self.position_slider.sliderMoved.connect(self._on_slider_moved)
        self.position_slider.sliderReleased.connect(self._on_slider_released)
        controls_layout.addWidget(self.position_slider, 1)  # 1 = stretch factor
        
        # Time display
        self.time_display = QLabel("00:00:00 / 00:00:00")
        self.time_display.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.time_display.setMinimumWidth(100)
        controls_layout.addWidget(self.time_display)
    
    def setup_shortcuts(self):
        """Set up keyboard shortcuts"""
        # Playback control
        QShortcut(QKeySequence("Space"), self).activated.connect(self.toggle_play)
        
        # Navigation shortcuts
        QShortcut(QKeySequence("Right"), self).activated.connect(
            lambda: self.seek_relative(1.0)
        )
        QShortcut(QKeySequence("Left"), self).activated.connect(
            lambda: self.seek_relative(-1.0)
        )
        QShortcut(QKeySequence("Shift+Right"), self).activated.connect(
            lambda: self.seek_relative(5.0)
        )
        QShortcut(QKeySequence("Shift+Left"), self).activated.connect(
            lambda: self.seek_relative(-5.0)
        )
        
        # Segment navigation
        QShortcut(QKeySequence("Ctrl+Right"), self).activated.connect(
            self.next_segment
        )
        QShortcut(QKeySequence("Ctrl+Left"), self).activated.connect(
            self.previous_segment
        )
        
        # Editing shortcuts
        QShortcut(QKeySequence("Ctrl+Shift+E"), self).activated.connect(
            self.edit_segment
        )
        QShortcut(QKeySequence("Ctrl+Shift+Delete"), self).activated.connect(
            self.remove_segment
        )
        QShortcut(QKeySequence("Ctrl+Shift+M"), self).activated.connect(
            self.merge_segments
        )
        QShortcut(QKeySequence("Ctrl+Shift+K"), self).activated.connect(
            self.split_segment
        )
        
        # Timing adjustment shortcuts
        QShortcut(QKeySequence("Alt+Left"), self).activated.connect(
            lambda: self.adjust_current_segment_timing(-0.1, 0)
        )
        QShortcut(QKeySequence("Alt+Right"), self).activated.connect(
            lambda: self.adjust_current_segment_timing(0.1, 0)
        )
        QShortcut(QKeySequence("Alt+Shift+Left"), self).activated.connect(
            lambda: self.adjust_current_segment_timing(0, -0.1)
        )
        QShortcut(QKeySequence("Alt+Shift+Right"), self).activated.connect(
            lambda: self.adjust_current_segment_timing(0, 0.1)
        )
    
    def populate_segment_list(self):
        """Fill the segment list with current subtitle segments"""
        self.segment_list.clear()
        
        for i, segment in enumerate(self.segments):
            item = SubtitleListItem(segment, i + 1)
            self.segment_list.addItem(item)
        
        # Update timeline visualization
        self.timeline.set_segments(self.segments)
        self.timeline.update()
    
    def select_segment(self, index: int):
        """Select a segment and update the editor"""
        if index != self.current_segment_index:
            self._edit_session += 1
        if index < 0 or index >= len(self.segments):
            # Clear editor if no valid segment
            self.current_segment_index = -1
            self.start_time_edit.setValue(0)
            self.end_time_edit.setValue(0)
            self.duration_label.setText("0.000 秒")
            self.original_text_edit.setPlainText("")
            self.translation_text_edit.setPlainText("")
            self.start_time_edit.setEnabled(False)
            self.end_time_edit.setEnabled(False)
            self.original_text_edit.setEnabled(False)
            self.translation_text_edit.setEnabled(False)
            return
        
        # Update current index
        self.current_segment_index = index
        segment = self.segments[index]
        
        # Update editor fields
        self.start_time_edit.setEnabled(True)
        self.end_time_edit.setEnabled(True)
        self.original_text_edit.setEnabled(True)
        self.translation_text_edit.setEnabled(True)
        
        # Block signals temporarily to avoid recursive updates
        self.start_time_edit.blockSignals(True)
        self.end_time_edit.blockSignals(True)
        self.original_text_edit.blockSignals(True)
        self.translation_text_edit.blockSignals(True)
        
        # Set values
        self.start_time_edit.setValue(segment.start_time)
        self.end_time_edit.setValue(segment.end_time)
        self.duration_label.setText(f"{segment.end_time - segment.start_time:.3f} 秒")
        self.original_text_edit.setPlainText(segment.original_text)
        self.translation_text_edit.setPlainText(segment.translated_text)
        
        # Unblock signals
        self.start_time_edit.blockSignals(False)
        self.end_time_edit.blockSignals(False)
        self.original_text_edit.blockSignals(False)
        self.translation_text_edit.blockSignals(False)
        
        # Update timeline selection
        self.timeline.set_selected_segment(index)
        
        # Optionally seek to the start of the segment
        if not self.is_playing:
            self.seek_to_position(segment.start_time)
    
    def select_segment_by_index(self, index: int):
        """Select a segment by its index (used by timeline clicks)"""
        if 0 <= index < self.segment_list.count():
            self.segment_list.setCurrentRow(index)
    
    def select_segment_by_time(self, time_position: float) -> int:
        """Find and select the segment that contains the given time position"""
        for i, segment in enumerate(self.segments):
            if segment.start_time <= time_position <= segment.end_time:
                self.select_segment_by_index(i)
                return i
        return -1
    
    def update_segment_timing(self):
        """Update the timing of the current segment"""
        if self.current_segment_index < 0 or self._history_restoring:
            return

        before_segments = self._last_history_state
        before_selection = self.current_segment_index
        start = self.start_time_edit.value()
        end = self.end_time_edit.value()
        
        # Ensure end time is not before start time
        if end < start:
            self.end_time_edit.blockSignals(True)
            self.end_time_edit.setValue(start)
            end = start
            self.end_time_edit.blockSignals(False)
        
        # Update segment
        segment = self.segments[self.current_segment_index]
        segment.start_time = start
        segment.end_time = end
        self._sync_processor_segments()
        
        # Update duration display
        self.duration_label.setText(f"{end - start:.3f} 秒")
        
        # Update list item display
        item = self.segment_list.item(self.current_segment_index)
        if isinstance(item, SubtitleListItem):
            item.update_display()
        
        # Update timeline
        self.timeline.update()
        
        # Signal that segments have changed
        self._push_history_change(
            "调整字幕时间",
            before_segments,
            before_selection,
            merge_key=("timing", self.current_segment_index, self._edit_session),
        )
        self.segmentsChanged.emit()
    
    def adjust_current_segment_timing(self, start_offset: float = 0, end_offset: float = 0):
        """Adjust timing of current segment by specified offsets"""
        if self.current_segment_index < 0:
            return
            
        # Get current values
        start = self.start_time_edit.value()
        end = self.end_time_edit.value()
        
        # Apply offsets
        new_start = max(0, start + start_offset)
        new_end = max(new_start, end + end_offset)
        
        # Update UI controls (which will trigger update_segment_timing)
        self.start_time_edit.setValue(new_start)
        self.end_time_edit.setValue(new_end)
    
    def update_segment_original_text(self):
        """Update the original text of the current segment"""
        if self.current_segment_index < 0 or self._history_restoring:
            return

        before_segments = self._last_history_state
        before_selection = self.current_segment_index
        # Update segment
        segment = self.segments[self.current_segment_index]
        segment.original_text = self.original_text_edit.toPlainText()
        self._sync_processor_segments()
        
        # Update list item display
        item = self.segment_list.item(self.current_segment_index)
        if isinstance(item, SubtitleListItem):
            item.update_display()

        self._push_history_change(
            "编辑字幕原文",
            before_segments,
            before_selection,
            merge_key=("original", self.current_segment_index, self._edit_session),
        )
        # Signal that segments have changed
        self.segmentsChanged.emit()
    
    def update_segment_translation(self):
        """Update the translated text of the current segment"""
        if self.current_segment_index < 0 or self._history_restoring:
            return

        before_segments = self._last_history_state
        before_selection = self.current_segment_index
        # Update segment
        segment = self.segments[self.current_segment_index]
        segment.translated_text = self.translation_text_edit.toPlainText()
        self._sync_processor_segments()
        self._push_history_change(
            "编辑字幕译文",
            before_segments,
            before_selection,
            merge_key=("translation", self.current_segment_index, self._edit_session),
        )
        # Signal that segments have changed
        self.segmentsChanged.emit()
    
    def add_segment(self):
        """Add a new segment"""
        before_segments = self._last_history_state
        before_selection = self.current_segment_index
        # Determine where to insert the new segment
        position = self.current_position
        
        # Create a new segment
        new_segment = SubtitleSegment(
            start_time=max(0, position - 0.5),  # Start 0.5s before current position
            end_time=position + 1.5,  # End 1.5s after current position
            original_text="",
            translated_text="",
            index=len(self.segments) + 1
        )
        
        # Add to segments list
        self.segments.append(new_segment)
        self._sync_processor_segments()
        
        # Add to UI
        item = SubtitleListItem(new_segment, len(self.segments))
        self.segment_list.addItem(item)
        
        # Select the new segment
        self.segment_list.setCurrentRow(len(self.segments) - 1)
        
        # Update timeline
        self.timeline.set_segments(self.segments)
        self.timeline.update()
        
        # Signal that segments have changed
        self._push_history_change(
            "添加字幕片段",
            before_segments,
            before_selection,
            after_selection=len(self.segments) - 1,
        )
        self.segmentsChanged.emit()
        
        # Set focus to text editor
        self.original_text_edit.setFocus()
    
    def remove_segment(self):
        """Remove the selected segment"""
        if self.current_segment_index < 0:
            return

        before_segments = self._last_history_state
        before_selection = self.current_segment_index
        # Remove from segments list
        self.segments.pop(self.current_segment_index)
        self._sync_processor_segments()
        
        # Remove from UI
        self.segment_list.takeItem(self.current_segment_index)
        
        # Update indices for remaining segments
        for i, segment in enumerate(self.segments):
            segment.index = i + 1
            item = self.segment_list.item(i)
            if isinstance(item, SubtitleListItem):
                item.index = i + 1
                item.update_display()
        
        # Select another segment if available
        if len(self.segments) > 0:
            new_index = min(self.current_segment_index, len(self.segments) - 1)
            self.segment_list.setCurrentRow(new_index)
        else:
            self.select_segment(-1)  # No segments left
        
        # Update timeline
        self.timeline.set_segments(self.segments)
        self.timeline.update()
        
        # Signal that segments have changed
        self._push_history_change(
            "删除字幕片段",
            before_segments,
            before_selection,
            after_selection=self.current_segment_index,
        )
        self.segmentsChanged.emit()
    
    def edit_segment(self):
        """Open detailed edit dialog for current segment"""
        if self.current_segment_index < 0:
            return

        before_segments = self._last_history_state
        before_selection = self.current_segment_index
        segment = self.segments[self.current_segment_index]
        dialog = SegmentEditDialog(segment, self)
        
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._sync_processor_segments()
            # Segment was updated in the dialog, update UI
            item = self.segment_list.item(self.current_segment_index)
            if isinstance(item, SubtitleListItem):
                item.update_display()
                
            # Also update the editor fields
            self.select_segment(self.current_segment_index)
            
            # Update timeline
            self.timeline.update()
            
            # Signal that segments have changed
            self._push_history_change(
                "编辑字幕片段",
                before_segments,
                before_selection,
            )
            self.segmentsChanged.emit()
    
    def merge_segments(self):
        """Merge selected segments"""
        # Get selected items
        selected_items = self.segment_list.selectedItems()
        if len(selected_items) < 2:
            # Need at least 2 segments to merge
            self.status_bar.setText("请至少选择 2 个连续字幕片段（Ctrl/⌘ 或 Shift 多选）")
            return
            
        # Get indices of selected items
        indices = sorted([self.segment_list.row(item) for item in selected_items])
        
        # Verify they are consecutive
        if indices[-1] - indices[0] + 1 != len(indices):
            self.status_bar.setText("只能合并连续的字幕片段")
            return

        before_segments = self._last_history_state
        before_selection = self.current_segment_index
        selected_after = indices[0]
        
        # Perform merge
        try:
            self.subtitle_processor.merge_segments(indices[0], indices[-1])

            # SubtitleProcessor replaces its list when merging; keep the
            # editor, timeline, and exporter on the new canonical list.
            self.segments = self.subtitle_processor.segments
            
            # Update UI
            self.populate_segment_list()
            
            # Select the merged segment
            self.segment_list.setCurrentRow(selected_after)
            
            # Signal that segments have changed
            self._push_history_change(
                "合并字幕片段",
                before_segments,
                before_selection,
                after_selection=selected_after,
            )
            self.segmentsChanged.emit()
            
            self.status_bar.setText(f"已合并 {len(indices)} 个字幕片段")
            
        except Exception as e:
            self.status_bar.setText(f"合并字幕失败：{str(e)}")
    
    def split_segment(self):
        """Split the selected segment at current position"""
        if self.current_segment_index < 0:
            return

        before_segments = self._last_history_state
        before_selection = self.current_segment_index
        selected_after = self.current_segment_index
        segment = self.segments[self.current_segment_index]
        
        # Check if current position is within segment
        if segment.start_time < self.current_position < segment.end_time:
            split_time = self.current_position
        else:
            # Split in the middle if current position is not within segment
            split_time = (segment.start_time + segment.end_time) / 2
            
        try:
            # Perform split
            self.subtitle_processor.split_segment(self.current_segment_index, split_time)

            # SubtitleProcessor replaces its list when splitting; refresh the
            # editor reference before rebuilding the list and exporting.
            self.segments = self.subtitle_processor.segments
            
            # Update UI
            self.populate_segment_list()
            
            # Select the first of the split segments
            self.segment_list.setCurrentRow(selected_after)
            
            # Signal that segments have changed
            self._push_history_change(
                "拆分字幕片段",
                before_segments,
                before_selection,
                after_selection=selected_after,
            )
            self.segmentsChanged.emit()
            
            self.status_bar.setText(f"已在 {split_time:.3f} 秒处拆分字幕")
            
        except Exception as e:
            self.status_bar.setText(f"拆分字幕失败：{str(e)}")
    
    def next_segment(self):
        """Select the next segment"""
        if self.current_segment_index < len(self.segments) - 1:
            self.segment_list.setCurrentRow(self.current_segment_index + 1)
    
    def previous_segment(self):
        """Select the previous segment"""
        if self.current_segment_index > 0:
            self.segment_list.setCurrentRow(self.current_segment_index - 1)
    
    def validate_subtitles(self):
        """Validate subtitles and show issues"""
        issues = self.subtitle_processor.validate_subtitles()
        
        if not issues:
            self.status_bar.setText("字幕检查通过，未发现问题")
            return
            
        # Count issues by type
        error_count = sum(1 for issue in issues if issue['type'] == 'error')
        warning_count = sum(1 for issue in issues if issue['type'] == 'warning')
        
        # Show summary in status bar
        self.status_bar.setText(
            f"发现 {len(issues)} 个问题：{error_count} 个错误，{warning_count} 个警告"
        )
        
        for issue in issues:
            segment_info = f"segment {issue['segment_idx'] + 1}" if issue['segment_idx'] is not None else "global"
            logger.warning(f"{issue['type'].upper()} in {segment_info}: {issue['message']}")

        dialog = SubtitleValidationDialog(issues, self)
        dialog.issueActivated.connect(self._focus_validation_issue)
        # Retain the latest dialog for accessibility tooling and UI tests.
        self._validation_dialog = dialog
        dialog.exec()

    def _focus_validation_issue(self, segment_idx: int):
        """Select and reveal the segment associated with a validation issue."""
        if not 0 <= segment_idx < self.segment_list.count():
            return
        self.segment_list.setCurrentRow(segment_idx)
        item = self.segment_list.item(segment_idx)
        self.segment_list.scrollToItem(item)
        self.original_text_edit.setFocus()
        self.status_bar.setText(f"已定位到第 {segment_idx + 1} 个字幕片段")
    
    def toggle_play(self):
        """Toggle video playback: use VLC"""
        # Protect against uninitialized VLC player
        if not hasattr(self, 'vlc_player') or self.vlc_player is None:
            if not is_vlc_available():
                self.status_bar.setText("当前环境未安装 VLC，仅提供静态画面预览")
            else:
                self.status_bar.setText("视频播放器尚未就绪")
            logger.info("尝试播放但 VLC 播放器未初始化")
            return
            
        # Toggle VLC playback only
        try:
            is_playing = bool(self.vlc_player.is_playing())
            if is_playing:
                # Pause playback and stop position update timer
                self.vlc_player.pause()
                self.is_playing = False
                if self.vlc_timer and self.vlc_timer.isActive():
                    self.vlc_timer.stop()
            else:
                # Start playback and resume position update timer
                self.vlc_player.play()
                self.is_playing = True
                if self.vlc_timer and not self.vlc_timer.isActive():
                    self.vlc_timer.start()
            # update UI text/icons
            self.play_button.setText("⏸" if self.is_playing else "▶")
            self.play_action.setText("暂停" if self.is_playing else "播放")
            self.playStateChanged.emit(self.is_playing)
        except Exception as e:
            logger.error(f"切换播放状态时出错: {str(e)}")
            self.status_bar.setText(f"播放错误: {str(e)}")
            self._media_fallback()
    
    def playback_state_changed(self, state):
        """Handle media player state changes"""
        # 修正 QMediaPlayer 状态枚举
        self.is_playing = (state == QMediaPlayer.PlayingState)
        
        # Update button text
        self.play_button.setText("⏸" if self.is_playing else "▶")
        self.play_action.setText("暂停" if self.is_playing else "播放")
        
        # Emit signal
        self.playStateChanged.emit(self.is_playing)
    
    def undo(self):
        """Undo the latest subtitle-model operation, regardless of focus."""
        self.undo_stack.undo()

    def redo(self):
        """Redo the latest subtitle-model operation, regardless of focus."""
        self.undo_stack.redo()
    
    def seek_to_position(self, position_seconds: float):
        """Seek to specific position in the video."""
        # 更新当前播放位置
        self.current_position = position_seconds
        if self.use_vlc_playback and self.vlc_player:
            ms = int(position_seconds*1000)
            self.vlc_player.set_time(ms)
            return
    
    def seek_relative(self, offset_seconds: float):
        """Seek relative to current position"""
        new_position = max(0, self.current_position + offset_seconds)
        self.seek_to_position(new_position)
    
    def update_subtitle_display(self):
        """Update the subtitle display based on current position"""
        if not self.segments:
            self.subtitle_display.setText("")
            self.subtitle_display.setVisible(False)
            return
            
        position = self.current_position
        found = False
        
        for segment in self.segments:
            if segment.start_time <= position <= segment.end_time:
                found = True
                
                # Determine what to display based on settings
                display_text = ""
                
                if self.show_original and segment.original_text:
                    display_text += segment.original_text
                    
                if self.show_translation and segment.translated_text:
                    if display_text:  # Add newline if we already have original text
                        display_text += "\n\n"
                    display_text += segment.translated_text
                
                self.subtitle_display.setText(display_text)
                self.subtitle_display.setVisible(bool(display_text))
                self.subtitle_overlay_layer.raise_()
                break
        
        if not found:
            self.subtitle_display.setText("")
            self.subtitle_display.setVisible(False)
    
    def toggle_original_display(self, show: bool):
        """Toggle display of original text in preview"""
        self.show_original = show
    
    def toggle_translation_display(self, show: bool):
        """Toggle display of translation in preview"""
        self.show_translation = show
    
    def handle_player_error(self, error, error_string=None):
        """Handle media player errors"""
        # 接收错误代码和可选错误字符串
        msg = error_string or self.media_player.errorString()
        logger.error(f"Media player error: {msg} (code: {error})")
        self.status_bar.setText(f"播放错误：{msg}")
        # 媒体加载失败时立即回退到静态图
        QTimer.singleShot(0, self._media_fallback)
    
    def get_processed_segments(self) -> List[SubtitleSegment]:
        """Get the current list of edited segments"""
        return self.segments

    def load_data(self, video_path: str, result_data: dict):
        """
        加载处理结果并初始化编辑器
        """
        self._invalidate_fallback_requests()

        # 标记加载来源 - 用于后续差异化处理
        is_project_import = result_data.get('is_project_import', False) or (video_path and video_path.lower().endswith('.vtp'))
        # # 如果导入的是与当前视频相同的项目文件，仅更新字幕列表，跳过播放器重置
        if is_project_import and hasattr(self, 'video_path') and \
            os.path.abspath(os.path.normcase(self.video_path)) == os.path.abspath(os.path.normcase(result_data.get('video_path', ''))):
            # ...只刷新字幕...
            raw_segments = result_data.get('segments', [])
            self.subtitle_processor.create_from_segments(raw_segments)
            self.segments = self.subtitle_processor.segments
            self.populate_segment_list()
            self.clear_undo_history()
            return

        # 【关键修复】在加载新视频之前，先清理旧的VLC实例
        # 这是修复视频切换时VLC全屏播放问题的关键步骤
        if hasattr(self, 'video_path') and self.video_path:
            logger.info(f"检测到视频切换：{getattr(self, 'video_path', 'None')} -> {video_path}")
            self._cleanup_vlc_player()
            logger.info("旧VLC实例已清理，准备加载新视频")

        # 1. 统一的视频路径解析逻辑
        if is_project_import:
            # 项目文件导入流程
            project_video_path = result_data.get('video_path', '')
            if not project_video_path or not os.path.exists(project_video_path):
                logger.error(f"项目中的视频路径无效: {project_video_path}")
                self.status_bar.setText("错误: 无法加载项目中的视频文件")
                # 尝试让用户选择视频文件
                from PyQt5.QtWidgets import QFileDialog
                new_path, _ = QFileDialog.getOpenFileName(
                    self, "选择视频文件", "", 
                    "视频文件 (*.mp4 *.avi *.mov *.mkv *.wmv *.flv);;所有文件 (*.*)"
                )
                if new_path:
                    video_path = new_path
                    logger.info(f"用户选择了新的视频文件: {video_path}")
                    
                    # 文件选择后重新获取窗口焦点
                    self.window().activateWindow()  # 激活主窗口
                    self.setFocus(Qt.OtherFocusReason)  # 为当前控件设置焦点
                    
                    # 强制处理事件以确保窗口状态更新
                    for _ in range(5):
                        QApplication.processEvents()
                    
                    # 添加延迟标记，用于后续增强VLC初始化稳定性
                    self._focus_restored_after_dialog = True
                else:
                    # 用户取消选择，设置标志指示无法加载视频
                    self.video_load_failed = True
                    return
            else:
                video_path = project_video_path
        elif not video_path:
            video_path = result_data.get('video_path')
        
        # 确保视频路径存在
        if not video_path or not os.path.exists(video_path):
            logger.error(f"无效的视频路径: {video_path}")
            self.status_bar.setText("错误: 视频文件不存在")
            self.video_load_failed = True
            return
            
        self.video_path = video_path
        
        # 2. 加载字幕数据 - 两种模式共用
        raw_segments = result_data.get("segments", [])
        self.subtitle_processor.create_from_segments(raw_segments)
        self.segments = self.subtitle_processor.segments
        
        # 3. 刷新界面显示
        self.populate_segment_list()
        self.clear_undo_history()
        
        # 4. 准备视频播放 - 在与用户交互完成后执行
        # 使用延时初始化确保窗口状态稳定
        self._scheduled_project_import = bool(is_project_import)
        self._playback_prepare_timer.start(500)
        
        # 5. 设置视频宽高比
        try:
            parent = self.parent()
            video_info = getattr(parent, 'workflow', None) and parent.workflow.get_data('video_info')
            if video_info and 'width' in video_info and 'height' in video_info and video_info['height']>0:
                self.video_aspect_ratio = video_info['width'] / video_info['height']
            else:
                self.video_aspect_ratio = None
        except Exception:
            self.video_aspect_ratio = None
            
        # 应用宽高比
        QTimer.singleShot(200, self._apply_aspect_ratio)

    def _prepare_video_playback(self, is_project_import=False):
        """统一的视频播放准备流程"""
        if self._is_closing:
            return
        # 首先清理任何现有的VLC实例（视频切换时的关键步骤）
        self._cleanup_vlc_player()
        
        # 确保视频窗口组件准备好接收视频输出
        self.video_widget.setVisible(True)
        self.video_stack.setCurrentWidget(self.video_widget)
        
        # 用户交互后特别加强窗口准备
        need_extra_focus = is_project_import or getattr(self, "_focus_restored_after_dialog", False)
        
        # 强制处理事件确保窗口更新，交互后的场景需要更多次数
        process_count = 5 if need_extra_focus else 3
        for _ in range(process_count):
            QApplication.processEvents()
        
        # 再次确保窗口获取焦点
        if need_extra_focus:
            self.window().activateWindow()
            self.video_widget.setFocus()
            QApplication.processEvents()
            # 使用更长的延迟确保窗口状态稳定
            self._scheduled_project_import = bool(is_project_import)
            self._vlc_init_timer.start(300)
        else:
            # 正常流程直接初始化
            self._init_vlc_playback(is_project_import)

    def _run_scheduled_playback_prepare(self):
        """Run QObject-owned delayed playback work only while the editor lives."""
        if not self._is_closing:
            self._prepare_video_playback(self._scheduled_project_import)

    def _run_scheduled_vlc_init(self):
        if not self._is_closing:
            self._init_vlc_playback(self._scheduled_project_import)

    def _init_vlc_playback(self, is_project_import=False):
        """重构的VLC初始化方法，适用于所有加载场景"""
        # 检查VLC可用性
        if not is_vlc_available():
            self.use_vlc_playback = False
            logger.info("VLC 不可用，改用静态画面预览")
            self.status_bar.setText("未检测到 VLC，已切换到静态画面预览")
            self._media_fallback()
            return
        
        # 【关键修复】在VLC初始化前，确保旧实例完全清理
        # 这是防止视频切换时VLC全屏播放的重要步骤
        if hasattr(self, 'vlc_player') and self.vlc_player:
            logger.warning("检测到未清理的VLC实例，强制清理中...")
            self._cleanup_vlc_player()
        
        # 【关键修复】强化窗口准备，确保嵌入模式稳定
        logger.info("准备窗口以接收新的VLC实例...")
        self.video_widget.setAttribute(Qt.WA_NativeWindow, True)
        self.video_widget.setAttribute(Qt.WA_DontCreateNativeAncestors, True)
        self.video_widget.setVisible(True)
        self.video_stack.setCurrentWidget(self.video_widget)
        
        # 强制处理事件确保窗口状态更新
        for i in range(3):
            QApplication.processEvents()
            if i < 2:  # 不在最后一次循环中sleep
                import time
                time.sleep(0.01)  # 短暂延迟让窗口系统稳定
        
        # 重新获取并验证窗口句柄
        try:
            win_id = int(self.video_widget.winId())
            logger.info(f"窗口句柄获取成功: {win_id}")
            if win_id <= 0:
                logger.error("窗口句柄无效，无法初始化VLC")
                self._media_fallback()
                return
        except Exception as e:
            logger.error(f"获取窗口句柄失败: {e}")
            self._media_fallback()
            return
        
        # 增强的VLC参数设置 - 确保视频嵌入并禁用内嵌字幕
        vlc_args = [
            '--intf', 'dummy',
            '--no-video-title-show',
            '--no-video-deco',
            '--embedded-video',
            '--no-fullscreen',
            '--no-keyboard-events',    # 禁用键盘事件以防止F键进入全屏
            '--no-mouse-events',       # 禁用鼠标事件以防止双击进入全屏
            '--no-xlib',
            '--no-spu',                # 禁用所有字幕轨道显示
            '--no-sub-autodetect-file' # 禁用字幕文件自动检测
        ]
        
        if plugins_path and os.path.isdir(plugins_path):
            vlc_args += ['--avcodec-hw=none']
        
        try:
            # 窗口准备已在上面完成，这里直接进行VLC实例创建
            logger.info(f"开始创建VLC实例，参数: {vlc_args}")
            
            # 项目导入时添加更多事件处理和时间
            process_count = 8 if is_project_import else 5
            for _ in range(process_count):  
                QApplication.processEvents()
            
            # 2. 获取窗口句柄并验证
            logger.info("VLC 初始化: 获取窗口句柄")
            win_id = int(self.video_widget.winId())
            logger.info(f"VLC 初始化: 窗口ID={win_id}")
            
            # 验证窗口句柄有效性
            if win_id == 0:
                logger.error("VLC 初始化: 窗口句柄无效")
                QApplication.processEvents()
                win_id = int(self.video_widget.winId())
                logger.info(f"VLC 初始化: 重新获取窗口ID={win_id}")
            
            # 3. 创建VLC实例
            logger.info("VLC 初始化: 开始创建实例")
            self.vlc_instance = vlc.Instance(vlc_args)
            logger.info(f"VLC 初始化: 实例创建结果={self.vlc_instance is not None}")
            
            if self.vlc_instance is None:
                logger.error("VLC 实例初始化失败")
                self._media_fallback()
                return
            
            # 4. 创建播放器并设置基本属性
            logger.info("VLC 初始化: 创建播放器")
            self.vlc_player = self.vlc_instance.media_player_new()
            self.vlc_player.set_fullscreen(False)
            
            # 5. 绑定窗口 - 关键步骤，必须在媒体加载前完成
            logger.info("VLC 初始化: 绑定窗口")
            
            # 在窗口绑定前强制重新获取焦点（对视频切换很重要）
            self.window().activateWindow()
            self.video_widget.setFocus()
            self.video_widget.show()
            self.video_widget.raise_()
            QApplication.processEvents()
            
            if sys.platform.startswith("win"):
                result = self.vlc_player.set_hwnd(win_id)
                logger.info(f"VLC 初始化: Windows窗口绑定结果={result}")
            elif sys.platform.startswith("linux"):
                result = self.vlc_player.set_xwindow(win_id)
                logger.info(f"VLC 初始化: Linux窗口绑定结果={result}")
            elif sys.platform == "darwin":
                result = self.vlc_player.set_nsobject(win_id)
                logger.info(f"VLC 初始化: macOS窗口绑定结果={result}")
            
            # 额外的窗口绑定验证
            QApplication.processEvents()
            
            # 6. 创建媒体对象
            logger.info(f"VLC 初始化: 创建媒体对象 - {self.video_path}")
            media = self.vlc_instance.media_new(self.video_path)
            if media is None:
                logger.error("VLC 媒体对象创建失败")
                self._media_fallback()
                return
            
            # 7. 设置媒体到播放器
            logger.info("VLC 初始化: 设置媒体到播放器")
            self.vlc_player.set_media(media)
            
            # 设置音量和事件处理
            logger.info("VLC 初始化: 设置音量和事件处理")
            self.vlc_player.audio_set_volume(100)
            
            # 显式禁用所有字幕轨道（双重保险）
            try:
                self.vlc_player.video_set_spu(-1)
                logger.info("VLC 初始化: 已显式禁用字幕轨道")
            except Exception as e:
                logger.warning(f"VLC 初始化: 禁用字幕轨道时出现错误: {e}")
            
            # 绑定事件处理
            em = self.vlc_player.event_manager()
            em.event_attach(vlc.EventType.MediaPlayerEndReached, 
                           lambda e: QTimer.singleShot(0, self._on_vlc_end))
            
            # 添加更多事件监听来诊断问题
            em.event_attach(vlc.EventType.MediaPlayerPlaying, 
                           lambda e: logger.info("VLC事件: 开始播放"))
            em.event_attach(vlc.EventType.MediaPlayerPaused, 
                           lambda e: logger.info("VLC事件: 暂停播放"))
            em.event_attach(vlc.EventType.MediaPlayerVout, 
                           lambda e: logger.info("VLC事件: 视频输出创建"))
            
            # 添加防止全屏/独立窗口的监测定时器
            self.fullscreen_check_timer = QTimer(self)
            self.fullscreen_check_timer.setInterval(200)
            self.fullscreen_check_timer.timeout.connect(self._enforce_embedded_mode)
            self.fullscreen_check_timer.start()
            
            # 设置位置更新定时器
            self.vlc_timer = QTimer(self)
            self.vlc_timer.setInterval(100)
            self.vlc_timer.timeout.connect(self._update_vlc_position)
            self.vlc_timer.start()
            
            # 预加载视频以获取元数据
            logger.info("VLC 初始化: 开始预加载视频")
            self.vlc_player.play()
            QTimer.singleShot(200, lambda: self.vlc_player.pause())
            QTimer.singleShot(500, self._initialize_vlc_metadata)
            
            # 延迟确保字幕被禁用（在视频开始播放后）
            QTimer.singleShot(1000, self._ensure_subtitles_disabled)
            
            # 额外的嵌入模式强制执行
            QTimer.singleShot(1500, self._force_embedded_mode)
            
            logger.info(f"VLC 播放器初始化成功: {self.video_path}")
            self.use_vlc_playback = True
            
        except Exception as e:
            logger.error(f"VLC 初始化失败: {str(e)}")
            self.use_vlc_playback = False
            self.status_bar.setText("VLC 初始化失败，已切换到静态画面预览")
            self._media_fallback()
            self.vlc_instance = None
            self.vlc_player = None

    def _enforce_embedded_mode(self):
        """确保VLC保持嵌入模式（定时检查）"""
        if not hasattr(self, 'vlc_player') or not self.vlc_player:
            return
            
        try:
            # 检查是否处于全屏模式，如果是则退出并重新绑定
            if self.vlc_player.get_fullscreen():
                logger.warning("检测到VLC进入全屏模式，强制退出全屏")
                self.vlc_player.set_fullscreen(False)
                
                # 重新绑定窗口
                win_id = int(self.video_widget.winId())
                if sys.platform.startswith("win"):
                    self.vlc_player.set_hwnd(win_id)
                elif sys.platform.startswith("linux"):
                    self.vlc_player.set_xwindow(win_id)
                elif sys.platform == "darwin":
                    self.vlc_player.set_nsobject(win_id)
                    
                logger.info("已强制VLC退出全屏模式并重新绑定窗口")
            
            # 同时确保字幕保持禁用状态
            try:
                current_spu = self.vlc_player.video_get_spu()
                if current_spu >= 0:  # 如果字幕被意外启用
                    self.vlc_player.video_set_spu(-1)
                    logger.info("检测到字幕被意外启用，已重新禁用")
            except Exception:
                pass
                
        except Exception as e:
            # 记录错误但不中断程序
            logger.debug(f"嵌入模式检查失败: {e}")
            pass

    def _media_fallback(self):
        """Start a generation-safe FFmpeg static-preview request."""
        self._invalidate_fallback_requests()
        if self._is_closing:
            return

        ffmpeg_path = shutil.which("ffmpeg")
        if ffmpeg_path is None:
            logger.warning("ffmpeg not found, cannot extract frame.")
            self._show_fallback_message("视频预览不可用：未找到 FFmpeg")
            return

        if not self.video_path or not os.path.isfile(self.video_path):
            logger.warning("视频文件不存在，无法提取首帧: %s", self.video_path)
            self._show_fallback_message("视频文件不存在")
            return

        request_id = self._fallback_generation
        video_path = os.path.abspath(self.video_path)
        self._show_fallback_message("正在生成静态预览…")
        task = _FrameExtractionTask(request_id, video_path, ffmpeg_path)
        self._fallback_tasks[request_id] = task
        task.signals.succeeded.connect(self._fallback_frame_ready)
        task.signals.failed.connect(self._fallback_frame_failed)
        self._fallback_thread_pool.start(task)

    def _invalidate_fallback_requests(self):
        """Make all earlier asynchronous frame results stale."""
        self._fallback_generation += 1

    def _show_fallback_message(self, message: str):
        self._fallback_source_pixmap = QPixmap()
        self.fallback_image_label.clear()
        self.fallback_image_label.setText(message)
        self.video_stack.setCurrentWidget(self.fallback_image_label)
        self.fallback_image_label.show()
        self.subtitle_overlay_layer.raise_()

    @pyqtSlot(int, str, bytes)
    def _fallback_frame_ready(
        self, request_id: int, video_path: str, frame_data: bytes
    ):
        self._fallback_tasks.pop(request_id, None)
        if (
            self._is_closing
            or request_id != self._fallback_generation
            or os.path.abspath(self.video_path or "") != os.path.abspath(video_path)
        ):
            return
        pixmap = QPixmap()
        if not pixmap.loadFromData(frame_data):
            self._show_fallback_message("视频预览不可用")
            return
        self._fallback_source_pixmap = pixmap
        self.fallback_image_label.setText("")
        self._scale_fallback_pixmap()
        self.video_stack.setCurrentWidget(self.fallback_image_label)
        self.fallback_image_label.show()
        self.subtitle_overlay_layer.raise_()

    @pyqtSlot(int, str, str)
    def _fallback_frame_failed(
        self, request_id: int, video_path: str, message: str
    ):
        self._fallback_tasks.pop(request_id, None)
        if (
            self._is_closing
            or request_id != self._fallback_generation
            or os.path.abspath(self.video_path or "") != os.path.abspath(video_path)
        ):
            return
        logger.warning("Fallback frame extract failed: %s", message)
        self._show_fallback_message("视频预览不可用")

    def _scale_fallback_pixmap(self):
        """Scale the retained source pixmap into the currently available box."""
        if self._fallback_source_pixmap.isNull():
            return
        size = self.fallback_image_label.contentsRect().size()
        if size.width() <= 0 or size.height() <= 0:
            size = self.video_stack.size()
        if size.width() <= 0 or size.height() <= 0:
            return
        self.fallback_image_label.setPixmap(
            self._fallback_source_pixmap.scaled(
                size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )

    def _update_timeline_duration(self):
        """Update timeline duration from media player if loaded"""
        duration_ms = self.media_player.duration()
        if duration_ms > 0:
            self.timeline.set_duration(duration_ms / 1000.0)

    def _check_playback_and_fallback(self):
        """在 Qt 或 VLC 不可用时明确降级到静态 FFmpeg 画面。"""
        if self.media_player and self.media_player.isVideoAvailable():
            # use QMediaPlayer
            self.use_vlc_playback = False
            return

        # Try VLC lazily. A static FFmpeg frame is the deterministic fallback.
        if not is_vlc_available():
            self.use_vlc_playback = False
            self.status_bar.setText("未检测到 VLC，仅提供静态画面预览")
            self._media_fallback()
            return

        try:
            self._init_vlc_playback()
            if hasattr(self, 'vlc_player') and self.vlc_player:
                self.use_vlc_playback = True
                return
        except Exception as e:
            logger.warning(f"VLC 初始化失败: {e}")

        self.use_vlc_playback = False
        self.status_bar.setText("视频播放不可用，仅提供静态画面预览")
        self._media_fallback()

    def _on_vlc_end(self):
        """Handle VLC end of media: reset to start"""
        # Stop VLC playback and timer, then reset UI
        if self.vlc_timer and self.vlc_timer.isActive():
            self.vlc_timer.stop()
        if self.vlc_player:
            self.vlc_player.stop()
        self.is_playing = False
        self.play_button.setText("▶")
        self.play_action.setText("播放")
        # Reset position
        self.current_position = 0.0
        self.position_slider.blockSignals(True)
        self.position_slider.setValue(0)
        self.position_slider.blockSignals(False)
        self.timeline.set_position(0.0)
        self.update_subtitle_display()
        self.update_time_display()

    def _update_vlc_position(self):
        """Poll VLC for current position"""
        if not self.vlc_player:
            return
        pos = self.vlc_player.get_time()
        dur = self.vlc_player.get_length()
        if dur > 0:
            self.current_position = pos/1000.0
            self.position_slider.blockSignals(True)
            self.position_slider.setValue(int((pos/dur)*1000))
            self.position_slider.blockSignals(False)
            self.update_time_display()
            self.timeline.set_position(self.current_position)
            self.update_subtitle_display()

    def _debug_media_status(self, status):
        """Debug slot for media status changes"""
        dur = self.media_player.duration()
        avail = self.media_player.isVideoAvailable()
        logger.debug(f"MediaStatusChanged: status={status}, duration={dur}, videoAvailable={avail}")
        if status == QMediaPlayer.LoadedMedia:
            self.video_stack.setCurrentWidget(self.video_widget)
    
    def _debug_video_available(self, available):
        """Debug slot for video availability changes"""
        logger.info(f"VideoAvailableChanged: available={available}")

    def resizeEvent(self, event):
        """Rescale a static fallback without constraining the editor layout."""
        super().resizeEvent(event)
        self._scale_fallback_pixmap()

    def _apply_aspect_ratio(self):
        """Refresh the fallback image within the layout-managed preview box."""
        self._scale_fallback_pixmap()

    def slider_position_changed(self, position):
        """Handle slider position change"""
        if self.use_vlc_playback:
            # Seek in VLC for preview
            val = position
            dur = self.vlc_player.get_length()
            if dur > 0:
                ms = int((val / 1000.0) * dur)
                self.vlc_player.set_time(ms)
                self.current_position = ms/1000.0
                # Sync UI elements
                self.timeline.set_position(self.current_position)
                self.update_subtitle_display()
                self.update_time_display()
            return

    def slider_released(self):
        """Handle slider release"""
        if self.use_vlc_playback:
            # VLC模式拖动进度：设置位置并渲染帧
            val = self.position_slider.value()
            dur = self.vlc_player.get_length()
            if dur > 0:
                ms = int((val / 1000.0) * dur)
                self.current_position = ms / 1000.0
                # Seek
                self.vlc_player.set_time(ms)
                # Sync UI
                self.timeline.set_position(self.current_position)
                self.update_subtitle_display()
                self.update_time_display()
                # After seeking, just set time; playback state is preserved
                # The new frame will be rendered automatically at the new position
            return

    def update_time_display(self):
        """Update the time display label based on current position and duration"""
        # Determine duration
        if self.use_vlc_playback and self.vlc_player:
            dur_ms = self.vlc_player.get_length() or 0
            position = self.current_position
            duration = dur_ms / 1000.0
        else:
            position = self.current_position
            duration = self.media_player.duration() / 1000.0 if self.media_player else 0
        # Format display
        from app.utils.format_converter import format_time
        pos_str = format_time(position, include_ms=False)
        dur_str = format_time(duration, include_ms=False)
        self.time_display.setText(f"{pos_str} / {dur_str}")

    def _initialize_vlc_metadata(self):
        """Initialize timeline duration and ensure slider seek works"""
        if not hasattr(self, 'vlc_player') or self.vlc_player is None:
            logger.warning("无法初始化 VLC 元数据: 播放器未初始化")
            self.status_bar.setText("警告: 无法获取视频时长信息")
            return
            
        try:
            dur = self.vlc_player.get_length() or 0
            if dur > 0:
                # 设置时间轴显示的总时长
                self.timeline.set_duration(dur / 1000.0)
                
                # 更新时间显示
                self.update_time_display()
        except Exception as e:
            logger.error(f"初始化 VLC 元数据时出错: {str(e)}")

    def _on_slider_pressed(self):
        """Record play state when user starts dragging slider"""
        # Record actual VLC playing state
        self.slider_was_playing = bool(self.vlc_player and self.vlc_player.is_playing())
        if self.slider_was_playing:
            self.vlc_player.pause()
            self.is_playing = False
            self.play_button.setText("▶")
            self.play_action.setText("播放")

    def _on_slider_moved(self, value: int):
        """Preview position as user drags the slider"""
        if self.use_vlc_playback and self.vlc_player:
            dur = self.vlc_player.get_length()
            if dur > 0:
                ms = int((value / 1000.0) * dur)
                self.vlc_player.set_time(ms)
                self.current_position = ms / 1000.0
                self.timeline.set_position(self.current_position)
                self.update_subtitle_display()
                self.update_time_display()

    def _on_slider_released(self):
        """Seek to final position and restore play state"""
        if self.use_vlc_playback and self.vlc_player:
            val = self.position_slider.value()
            dur = self.vlc_player.get_length()
            if dur > 0:
                ms = int((val / 1000.0) * dur)
                self.current_position = ms / 1000.0
                self.vlc_player.set_time(ms)
                # Restore play state
                if hasattr(self, 'slider_was_playing') and self.slider_was_playing:
                    self.vlc_player.play()
                    self.is_playing = True
                    self.play_button.setText("⏸")
                    self.play_action.setText("暂停")
                else:
                    self.vlc_player.pause()
                    self.is_playing = False
                self.timeline.set_position(self.current_position)
                self.update_subtitle_display()
                self.update_time_display()
            # clear flag
            self.slider_was_playing = False

    def _ensure_subtitles_disabled(self):
        """确保VLC的内嵌字幕被禁用"""
        if not hasattr(self, 'vlc_player') or not self.vlc_player:
            return
            
        try:
            # 获取当前字幕轨道信息
            spu_count = self.vlc_player.video_get_spu_count()
            current_spu = self.vlc_player.video_get_spu()
            
            if spu_count > 0 and current_spu >= 0:
                # 如果有字幕轨道且当前启用了字幕，则禁用
                logger.info(f"检测到视频有 {spu_count} 个字幕轨道，当前轨道: {current_spu}")
                self.vlc_player.video_set_spu(-1)
                logger.info("已禁用VLC内嵌字幕显示")
                
                # 验证禁用是否成功
                new_spu = self.vlc_player.video_get_spu()
                if new_spu < 0:
                    logger.debug("内嵌字幕禁用成功")
                else:
                    logger.warning(f"内嵌字幕可能未完全禁用，当前轨道: {new_spu}")
            elif spu_count == 0:
                logger.debug("视频没有内嵌字幕轨道")
            else:
                logger.debug("字幕轨道已被禁用")
                
        except Exception as e:
            logger.debug(f"检查字幕轨道时出错（可忽略）: {e}")

    def _force_embedded_mode(self):
        """强制确保VLC在嵌入模式下运行"""
        if not hasattr(self, 'vlc_player') or not self.vlc_player:
            return
            
        try:
            # 检查并强制退出全屏模式
            if self.vlc_player.get_fullscreen():
                logger.warning("VLC 处于全屏模式，强制退出")
                self.vlc_player.set_fullscreen(False)
                
                # 重新绑定窗口句柄
                win_id = int(self.video_widget.winId())
                if sys.platform.startswith("win"):
                    result = self.vlc_player.set_hwnd(win_id)
                    logger.info(f"重新绑定Windows窗口，结果={result}")
                elif sys.platform.startswith("linux"):
                    result = self.vlc_player.set_xwindow(win_id)
                    logger.info(f"重新绑定Linux窗口，结果={result}")
                elif sys.platform == "darwin":
                    result = self.vlc_player.set_nsobject(win_id)
                    logger.info(f"重新绑定macOS窗口，结果={result}")
                
                # 强制更新窗口
                self.video_widget.update()
                self.video_widget.repaint()
                QApplication.processEvents()
                
                logger.info("已强制VLC退出全屏模式并重新绑定窗口")
            else:
                logger.info("VLC 已在嵌入模式运行")
                
        except Exception as e:
            logger.error(f"强制嵌入模式失败: {e}")

    def _cleanup_vlc_player(self):
        """完全清理VLC播放器和相关资源"""
        try:
            # 停止所有定时器
            if hasattr(self, 'vlc_timer') and self.vlc_timer:
                self.vlc_timer.stop()
                self.vlc_timer.deleteLater()
                self.vlc_timer = None
                
            if hasattr(self, 'fullscreen_check_timer') and self.fullscreen_check_timer:
                self.fullscreen_check_timer.stop()
                self.fullscreen_check_timer.deleteLater()
                self.fullscreen_check_timer = None
                
            # 停止VLC播放器
            if hasattr(self, 'vlc_player') and self.vlc_player:
                try:
                    self.vlc_player.stop()
                    # 解除窗口绑定
                    if sys.platform.startswith("win"):
                        self.vlc_player.set_hwnd(0)
                    elif sys.platform.startswith("linux"):
                        self.vlc_player.set_xwindow(0)
                    elif sys.platform == "darwin":
                        self.vlc_player.set_nsobject(0)
                except Exception as e:
                    logger.debug(f"清理VLC播放器时出现错误: {e}")
                finally:
                    self.vlc_player = None
                    
            # 清理VLC实例
            if hasattr(self, 'vlc_instance') and self.vlc_instance:
                try:
                    self.vlc_instance.release()
                except Exception as e:
                    logger.debug(f"清理VLC实例时出现错误: {e}")
                finally:
                    self.vlc_instance = None
                    
            # 重置播放状态
            self.is_playing = False
            self.current_position = 0.0
            
            logger.info("VLC播放器已完全清理")
            
        except Exception as e:
            logger.error(f"清理VLC播放器时发生错误: {e}")

    def closeEvent(self, event):
        """Invalidate background preview callbacks before Qt destroys widgets."""
        self.shutdown_media_preview()
        super().closeEvent(event)

    def shutdown_media_preview(self):
        """Stop accepting preview results during application shutdown."""
        self._is_closing = True
        self._playback_prepare_timer.stop()
        self._vlc_init_timer.stop()
        self._invalidate_fallback_requests()
        self.subtitle_timer.stop()
        self._cleanup_vlc_player()

# 添加类别名，使SubtitleEditor指向SubtitleEditor
SubtitleEditorWidget = SubtitleEditor  # 兼容性别名
