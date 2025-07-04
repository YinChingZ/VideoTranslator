#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Subtitle Editor GUI module for video translation system.
Provides interface for editing subtitles with video preview.
"""

import os
import sys
import logging
from typing import List, Dict, Optional, Tuple, Any, Callable

from PyQt5.QtCore import (
    Qt, QUrl, QTime, QTimer, QSize, pyqtSignal, QEvent,
    QPropertyAnimation, QEasingCurve, QPoint, QModelIndex
)
from PyQt5.QtGui import (
    QFont, QColor, QPalette, QKeySequence,
    QPainter, QPen, QTextCursor, QTextCharFormat, QPixmap, QImage
)
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QLabel,
    QPushButton, QScrollArea, QTextEdit, QListWidget, QListWidgetItem,
    QSlider, QComboBox, QToolBar, QSpinBox, QDoubleSpinBox, QColorDialog,
    QMenu, QDialog, QDialogButtonBox, QGridLayout, QGroupBox, QCheckBox,
    QToolButton, QSizePolicy, QFrame, QShortcut, QApplication, QStackedWidget
)
from PyQt5.QtMultimedia import QMediaPlayer, QMediaContent
from PyQt5.QtMultimediaWidgets import QVideoWidget
import cv2
# Add VLC DLL search path on Windows before importing vlc
libvlc_path = None
plugins_path = None
if sys.platform.startswith("win"):
    # 直接指定VLC路径并添加到DLL搜索目录和环境变量PATH
    vlc_paths = [
        os.environ.get("VLC_DIR"),
        r"C:\Program Files\VideoLAN\VLC",
        r"C:\Program Files (x86)\VideoLAN\VLC"
    ]
    
    # 先导入logging
    import logging
    logger = logging.getLogger(__name__)
    
    # 找到并使用有效的VLC路径
    for path in vlc_paths:
        if path and os.path.isdir(path):
            os.add_dll_directory(path)
            # 同时添加到PATH环境变量
            if path not in os.environ.get('PATH', ''):
                os.environ['PATH'] = path + os.pathsep + os.environ.get('PATH', '')
            # 记录路径，用于后续初始化
            libvlc_path = path
            plugins_path = os.path.join(path, 'plugins')
            logger.info(f"已添加VLC目录: {path}")
            break
import vlc

import tempfile, uuid, shutil

# 检查 VLC 是否可用的函数
def is_vlc_available():
    """检查 VLC 库是否可用"""
    try:
        # 尝试创建一个简单的 VLC 实例
        test_instance = vlc.Instance(['--quiet'])
        if test_instance is None:
            return False
        # 检查是否可以创建媒体播放器
        test_player = test_instance.media_player_new()
        if test_player is None:
            return False
        return True
    except Exception as e:
        logger.error(f"VLC 不可用: {str(e)}")
        return False

# 在启动时检查 VLC 可用性
vlc_available = is_vlc_available()

# Import custom modules
from app.core.subtitle import SubtitleProcessor, SubtitleSegment
from app.gui.custom_widgets import TimelineWidget, WaveformView
from app.utils.format_converter import format_time, parse_time

# 定义临时图片路径
temp_img = os.path.join(tempfile.gettempdir(), f"frame_{uuid.uuid4().hex}.jpg")

logger = logging.getLogger(__name__)


class SubtitleListItem(QListWidgetItem):
    """Custom list widget item to represent subtitle segments"""
    
    def __init__(self, segment: SubtitleSegment, index: int):
        super().__init__()
        self.segment = segment
        self.index = index
        self.update_display()
        
    def update_display(self):
        """Update the displayed text based on segment data"""
        start_time = format_time(self.segment.start_time)
        end_time = format_time(self.segment.end_time)
        
        # Truncate text for display if too long
        orig_text = self.segment.original_text
        if len(orig_text) > 40:
            orig_text = orig_text[:37] + "..."
        
        display_text = f"{self.index}. [{start_time} - {end_time}] {orig_text}"
        self.setText(display_text)


class SegmentEditDialog(QDialog):
    """Dialog for detailed editing of a subtitle segment"""
    
    def __init__(self, segment: SubtitleSegment, parent=None):
        super().__init__(parent)
        self.segment = segment
        self.setWindowTitle("Edit Subtitle Segment")
        self.setup_ui()
        
    def setup_ui(self):
        """Set up the dialog UI components"""
        layout = QGridLayout(self)
        
        # Time controls
        time_group = QGroupBox("Timing")
        time_layout = QGridLayout()
        
        # Start time
        time_layout.addWidget(QLabel("Start Time:"), 0, 0)
        self.start_time = QDoubleSpinBox()
        self.start_time.setDecimals(3)
        self.start_time.setRange(0, 86400)  # 24 hours max
        self.start_time.setValue(self.segment.start_time)
        self.start_time.setSingleStep(0.1)
        time_layout.addWidget(self.start_time, 0, 1)
        
        # End time
        time_layout.addWidget(QLabel("End Time:"), 1, 0)
        self.end_time = QDoubleSpinBox()
        self.end_time.setDecimals(3)
        self.end_time.setRange(0, 86400)  # 24 hours max
        self.end_time.setValue(self.segment.end_time)
        self.end_time.setSingleStep(0.1)
        time_layout.addWidget(self.end_time, 1, 1)
        
        # Duration (calculated)
        time_layout.addWidget(QLabel("Duration:"), 2, 0)
        self.duration = QLabel(f"{self.segment.end_time - self.segment.start_time:.3f} seconds")
        time_layout.addWidget(self.duration, 2, 1)
        
        # Connect signals to update duration
        self.start_time.valueChanged.connect(self.update_duration)
        self.end_time.valueChanged.connect(self.update_duration)
        
        time_group.setLayout(time_layout)
        layout.addWidget(time_group, 0, 0, 1, 2)
        
        # Text editing
        text_group = QGroupBox("Text")
        text_layout = QVBoxLayout()
        
        # Original text
        text_layout.addWidget(QLabel("Original Text:"))
        self.original_text = QTextEdit()
        self.original_text.setPlainText(self.segment.original_text)
        text_layout.addWidget(self.original_text)
        
        # Translated text
        text_layout.addWidget(QLabel("Translated Text:"))
        self.translated_text = QTextEdit()
        self.translated_text.setPlainText(self.segment.translated_text)
        text_layout.addWidget(self.translated_text)
        
        text_group.setLayout(text_layout)
        layout.addWidget(text_group, 1, 0, 1, 2)
        
        # Style options
        style_group = QGroupBox("Style (Advanced)")
        style_layout = QGridLayout()
        
        # Font size
        style_layout.addWidget(QLabel("Font Size:"), 0, 0)
        self.font_size = QSpinBox()
        self.font_size.setRange(8, 72)
        
        # Set initial value from segment style or default
        if self.segment.style and 'fontsize' in self.segment.style:
            self.font_size.setValue(int(self.segment.style['fontsize']))
        else:
            self.font_size.setValue(24)  # Default font size
            
        style_layout.addWidget(self.font_size, 0, 1)
        
        # Text color
        style_layout.addWidget(QLabel("Text Color:"), 1, 0)
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
        color = QColorDialog.getColor(self.current_color, self, "Select Text Color")
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
        self.duration.setText(f"{duration:.3f} seconds")
    
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
        
        # Ensure media_player attribute exists for seek_to_position
        self.media_player = None
        
        # Subtitle display options
        self.show_original = True
        self.show_translation = True
        
        # Playback backend: only use VLC for audio/video
        self.vlc_instance = None
        self.vlc_player = None
        self.vlc_timer = None
        self.use_vlc_playback = True
        
        # Initialize UI
        self.init_ui()
        
        # Set up timer for subtitle display updates
        self.subtitle_timer = QTimer(self)
        self.subtitle_timer.setInterval(100)  # Check subtitle display every 100ms
        self.subtitle_timer.timeout.connect(self.update_subtitle_display)
        self.subtitle_timer.start()
        
        # Media player will be initialized when data loaded
        # self.setup_media_player()
    
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
        # Removed minimum height to allow more space for video
        self.fallback_image_label = QLabel()
        self.fallback_image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.fallback_image_label.setVisible(False)
        self.fallback_image_label.setScaledContents(False)
        # Stacked widget for video and fallback
        self.video_stack = QStackedWidget()
        self.video_stack.addWidget(self.video_widget)
        self.video_stack.addWidget(self.fallback_image_label)
        # Allow video_stack to expand both directions, maintain aspect via resizeEvent
        self.video_stack.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        video_layout.addWidget(self.video_stack)
        # Ensure video preview area is large enough
        self.video_container.setMinimumHeight(300)
        
        # Current subtitle display overlay
        self.subtitle_display = QLabel()
        self.subtitle_display.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.subtitle_display.setStyleSheet(
            "background-color: rgba(0, 0, 0, 100);"
            "color: white;"
            "padding: 8px;"
            "border-radius: 4px;"
        )
        self.subtitle_display.setWordWrap(True)
        video_layout.addWidget(self.subtitle_display)
        
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
        
        segment_list_header = QLabel("Subtitle Segments")
        segment_list_header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        segment_list_layout.addWidget(segment_list_header)
        
        self.segment_list = QListWidget()
        self.segment_list.setAlternatingRowColors(True)
        self.segment_list.currentRowChanged.connect(self.select_segment)
        self.segment_list.itemDoubleClicked.connect(self.edit_segment)
        segment_list_layout.addWidget(self.segment_list)
        
        # Segment list control buttons
        segment_btn_layout = QHBoxLayout()
        
        self.add_segment_btn = QPushButton("Add")
        self.add_segment_btn.clicked.connect(self.add_segment)
        segment_btn_layout.addWidget(self.add_segment_btn)
        
        self.remove_segment_btn = QPushButton("Remove")
        self.remove_segment_btn.clicked.connect(self.remove_segment)
        segment_btn_layout.addWidget(self.remove_segment_btn)
        
        self.merge_segments_btn = QPushButton("Merge")
        self.merge_segments_btn.clicked.connect(self.merge_segments)
        segment_btn_layout.addWidget(self.merge_segments_btn)
        
        self.split_segment_btn = QPushButton("Split")
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
        
        timing_layout.addWidget(QLabel("Start Time:"), 0, 0)
        self.start_time_edit = QDoubleSpinBox()
        self.start_time_edit.setDecimals(3)
        self.start_time_edit.setRange(0, 86400)  # 24 hours max
        self.start_time_edit.setSingleStep(0.1)
        self.start_time_edit.valueChanged.connect(self.update_segment_timing)
        timing_layout.addWidget(self.start_time_edit, 0, 1)
        
        timing_layout.addWidget(QLabel("End Time:"), 0, 2)
        self.end_time_edit = QDoubleSpinBox()
        self.end_time_edit.setDecimals(3)
        self.end_time_edit.setRange(0, 86400)  # 24 hours max
        self.end_time_edit.setSingleStep(0.1)
        self.end_time_edit.valueChanged.connect(self.update_segment_timing)
        timing_layout.addWidget(self.end_time_edit, 0, 3)
        
        timing_layout.addWidget(QLabel("Duration:"), 0, 4)
        self.duration_label = QLabel("0.000 s")
        timing_layout.addWidget(self.duration_label, 0, 5)
        
        editor_layout.addLayout(timing_layout)
        
        # Text editors
        text_splitter = QSplitter(Qt.Orientation.Vertical)
        
        # Original text
        original_container = QWidget()
        original_layout = QVBoxLayout(original_container)
        original_layout.setContentsMargins(0, 0, 0, 0)
        
        original_header = QLabel("Original Text:")
        original_layout.addWidget(original_header)
        
        self.original_text_edit = QTextEdit()
        self.original_text_edit.textChanged.connect(self.update_segment_original_text)
        original_layout.addWidget(self.original_text_edit)
        
        text_splitter.addWidget(original_container)
        
        # Translated text
        translation_container = QWidget()
        translation_layout = QVBoxLayout(translation_container)
        translation_layout.setContentsMargins(0, 0, 0, 0)
        
        translation_header = QLabel("Translated Text:")
        translation_layout.addWidget(translation_header)
        
        self.translation_text_edit = QTextEdit()
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
        self.status_bar = QLabel("Ready")
        self.status_bar.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.status_bar.setStyleSheet("padding: 2px; background-color: #f0f0f0;")
        main_layout.addWidget(self.status_bar)
        
        # Load segments into UI
        self.populate_segment_list()
        
        # Set keyboard shortcuts
        self.setup_shortcuts()
    
    def create_toolbar(self):
        """Create the toolbar with common actions"""
        self.toolbar = QToolBar()
        self.toolbar.setMovable(False)
        
        # Playback controls
        self.play_action = self.toolbar.addAction("Play")
        self.play_action.triggered.connect(self.toggle_play)
        
        self.toolbar.addSeparator()
        
        # Add timing adjustment buttons
        self.toolbar.addAction("←0.1s").triggered.connect(
            lambda: self.adjust_current_segment_timing(-0.1, 0)
        )
        self.toolbar.addAction("→0.1s").triggered.connect(
            lambda: self.adjust_current_segment_timing(0.1, 0)
        )
        self.toolbar.addSeparator()
        self.toolbar.addAction("←0.1s").triggered.connect(
            lambda: self.adjust_current_segment_timing(0, -0.1)
        )
        self.toolbar.addAction("→0.1s").triggered.connect(
            lambda: self.adjust_current_segment_timing(0, 0.1)
        )
        
        self.toolbar.addSeparator()
        
        # View options
        self.show_original_action = self.toolbar.addAction("Show Original")
        self.show_original_action.setCheckable(True)
        self.show_original_action.setChecked(True)
        self.show_original_action.toggled.connect(self.toggle_original_display)
        
        self.show_translation_action = self.toolbar.addAction("Show Translation")
        self.show_translation_action.setCheckable(True)
        self.show_translation_action.setChecked(True)
        self.show_translation_action.toggled.connect(self.toggle_translation_display)
        
        self.toolbar.addSeparator()
        
        # Validate action
        self.validate_action = self.toolbar.addAction("Validate")
        self.validate_action.triggered.connect(self.validate_subtitles)
    
    def create_video_controls(self):
        """Create video playback controls"""
        self.video_controls = QWidget()
        controls_layout = QHBoxLayout(self.video_controls)
        controls_layout.setContentsMargins(0, 0, 0, 0)
        
        # Skip back 1s button
        self.back_button = QPushButton("⏪ 1s")
        self.back_button.clicked.connect(lambda: self.seek_relative(-1.0))
        controls_layout.addWidget(self.back_button)
        # Play/pause button
        self.play_button = QPushButton("▶")
        self.play_button.clicked.connect(self.toggle_play)
        controls_layout.addWidget(self.play_button)
        # Skip forward 1s button
        self.forward_button = QPushButton("1s ⏩")
        self.forward_button.clicked.connect(lambda: self.seek_relative(1.0))
        controls_layout.addWidget(self.forward_button)

        # Position slider (full width)
        self.position_slider = QSlider(Qt.Orientation.Horizontal)
        self.position_slider.setRange(0, 1000)
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
        QShortcut(QKeySequence("Ctrl+E"), self).activated.connect(
            self.edit_segment
        )
        QShortcut(QKeySequence("Ctrl+D"), self).activated.connect(
            self.remove_segment
        )
        QShortcut(QKeySequence("Ctrl+M"), self).activated.connect(
            self.merge_segments
        )
        QShortcut(QKeySequence("Ctrl+S"), self).activated.connect(
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
        if index < 0 or index >= len(self.segments):
            # Clear editor if no valid segment
            self.current_segment_index = -1
            self.start_time_edit.setValue(0)
            self.end_time_edit.setValue(0)
            self.duration_label.setText("0.000 s")
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
        self.duration_label.setText(f"{segment.end_time - segment.start_time:.3f} s")
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
        if self.current_segment_index < 0:
            return
            
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
        
        # Update duration display
        self.duration_label.setText(f"{end - start:.3f} s")
        
        # Update list item display
        item = self.segment_list.item(self.current_segment_index)
        if isinstance(item, SubtitleListItem):
            item.update_display()
        
        # Update timeline
        self.timeline.update()
        
        # Signal that segments have changed
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
        if self.current_segment_index < 0:
            return
            
        # Update segment
        segment = self.segments[self.current_segment_index]
        segment.original_text = self.original_text_edit.toPlainText()
        
        # Update list item display
        item = self.segment_list.item(self.current_segment_index)
        if isinstance(item, SubtitleListItem):
            item.update_display()
            
        # Signal that segments have changed
        self.segmentsChanged.emit()
    
    def update_segment_translation(self):
        """Update the translated text of the current segment"""
        if self.current_segment_index < 0:
            return
            
        # Update segment
        segment = self.segments[self.current_segment_index]
        segment.translated_text = self.translation_text_edit.toPlainText()
            
        # Signal that segments have changed
        self.segmentsChanged.emit()
    
    def add_segment(self):
        """Add a new segment"""
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
        
        # Add to UI
        item = SubtitleListItem(new_segment, len(self.segments))
        self.segment_list.addItem(item)
        
        # Select the new segment
        self.segment_list.setCurrentRow(len(self.segments) - 1)
        
        # Update timeline
        self.timeline.set_segments(self.segments)
        self.timeline.update()
        
        # Signal that segments have changed
        self.segmentsChanged.emit()
        
        # Set focus to text editor
        self.original_text_edit.setFocus()
    
    def remove_segment(self):
        """Remove the selected segment"""
        if self.current_segment_index < 0:
            return
            
        # Remove from segments list
        self.segments.pop(self.current_segment_index)
        
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
        self.segmentsChanged.emit()
    
    def edit_segment(self):
        """Open detailed edit dialog for current segment"""
        if self.current_segment_index < 0:
            return
            
        segment = self.segments[self.current_segment_index]
        dialog = SegmentEditDialog(segment, self)
        
        if dialog.exec() == QDialog.DialogCode.Accepted:
            # Segment was updated in the dialog, update UI
            item = self.segment_list.item(self.current_segment_index)
            if isinstance(item, SubtitleListItem):
                item.update_display()
                
            # Also update the editor fields
            self.select_segment(self.current_segment_index)
            
            # Update timeline
            self.timeline.update()
            
            # Signal that segments have changed
            self.segmentsChanged.emit()
    
    def merge_segments(self):
        """Merge selected segments"""
        # Get selected items
        selected_items = self.segment_list.selectedItems()
        if len(selected_items) < 2:
            # Need at least 2 segments to merge
            self.status_bar.setText("Select at least 2 segments to merge (Ctrl+click to select multiple)")
            return
            
        # Get indices of selected items
        indices = sorted([self.segment_list.row(item) for item in selected_items])
        
        # Verify they are consecutive
        if indices[-1] - indices[0] + 1 != len(indices):
            self.status_bar.setText("Can only merge consecutive segments")
            return
        
        # Perform merge
        try:
            self.subtitle_processor.merge_segments(indices[0], indices[-1])
            
            # Update UI
            self.populate_segment_list()
            
            # Select the merged segment
            self.segment_list.setCurrentRow(indices[0])
            
            # Signal that segments have changed
            self.segmentsChanged.emit()
            
            self.status_bar.setText(f"Merged {len(indices)} segments")
            
        except Exception as e:
            self.status_bar.setText(f"Error merging segments: {str(e)}")
    
    def split_segment(self):
        """Split the selected segment at current position"""
        if self.current_segment_index < 0:
            return
            
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
            
            # Update UI
            self.populate_segment_list()
            
            # Select the first of the split segments
            self.segment_list.setCurrentRow(self.current_segment_index)
            
            # Signal that segments have changed
            self.segmentsChanged.emit()
            
            self.status_bar.setText(f"Split segment at {split_time:.3f}s")
            
        except Exception as e:
            self.status_bar.setText(f"Error splitting segment: {str(e)}")
    
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
            self.status_bar.setText("No issues found in subtitles")
            return
            
        # Count issues by type
        error_count = sum(1 for issue in issues if issue['type'] == 'error')
        warning_count = sum(1 for issue in issues if issue['type'] == 'warning')
        
        # Show summary in status bar
        self.status_bar.setText(
            f"Found {len(issues)} issues: {error_count} errors, {warning_count} warnings"
        )
        
        # TODO: Show detailed validation results in a dialog
        # For now, just log them
        for issue in issues:
            segment_info = f"segment {issue['segment_idx'] + 1}" if issue['segment_idx'] is not None else "global"
            logger.warning(f"{issue['type'].upper()} in {segment_info}: {issue['message']}")
    
    def toggle_play(self):
        """Toggle video playback: use VLC"""
        # Protect against uninitialized VLC player
        if not hasattr(self, 'vlc_player') or self.vlc_player is None:
            self.status_bar.setText("错误: 视频播放器未初始化")
            logger.error("尝试播放但 VLC 播放器未初始化")
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
            self.play_action.setText("Pause" if self.is_playing else "Play")
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
        self.play_action.setText("Pause" if self.is_playing else "Play")
        
        # Emit signal
        self.playStateChanged.emit(self.is_playing)
    
    def undo(self):
        """Stub for undo action"""
        # 调用文本编辑框撤销
        if self.original_text_edit.hasFocus():
            self.original_text_edit.undo()
        elif self.translation_text_edit.hasFocus():
            self.translation_text_edit.undo()
    
    def redo(self):
        """Stub for redo action"""
        # 调用文本编辑框重做
        if self.original_text_edit.hasFocus():
            self.original_text_edit.redo()
        elif self.translation_text_edit.hasFocus():
            self.translation_text_edit.redo()
    
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
                break
        
        if not found:
            self.subtitle_display.setText("")
    
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
        self.status_bar.setText(f"Error: {msg}")
        # 媒体加载失败时立即回退到静态图
        QTimer.singleShot(0, self._media_fallback)
    
    def get_processed_segments(self) -> List[SubtitleSegment]:
        """Get the current list of edited segments"""
        return self.segments

    def load_data(self, video_path: str, result_data: dict):
        """
        加载处理结果并初始化编辑器
        """
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
        
        # 4. 准备视频播放 - 在与用户交互完成后执行
        # 使用延时初始化确保窗口状态稳定
        QTimer.singleShot(500, lambda: self._prepare_video_playback(is_project_import))
        
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
            QTimer.singleShot(300, lambda: self._init_vlc_playback(is_project_import))
        else:
            # 正常流程直接初始化
            self._init_vlc_playback(is_project_import)

    def _init_vlc_playback(self, is_project_import=False):
        """重构的VLC初始化方法，适用于所有加载场景"""
        # 检查VLC可用性
        if not vlc_available:
            logger.error("VLC 不可用，无法初始化播放器")
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
            
        except Exception as e:
            logger.error(f"VLC 初始化失败: {str(e)}")
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
        """Fallback to show first frame via ffmpeg if media not available"""
        # 保存临时图像的路径
        global temp_img
        temp_img = os.path.join(tempfile.gettempdir(), f"frame_{uuid.uuid4().hex}.jpg")
        
        # use mktemp to avoid file lock issues
        if shutil.which('ffmpeg') is None:
            logger.warning("ffmpeg not found, cannot extract frame.")
            self.fallback_image_label.setText("视频预览不可用")
            self.fallback_image_label.setVisible(True)
            self.fallback_image_label.raise_()
            self.video_widget.setVisible(False)
            return
            
        # 确保视频路径有效
        if not self.video_path or not os.path.exists(self.video_path):
            logger.warning(f"视频文件不存在，无法提取首帧: {self.video_path}")
            self.fallback_image_label.setText("视频文件不存在")
            self.fallback_image_label.setVisible(True)
            self.fallback_image_label.raise_()
            self.video_widget.setVisible(False)
            return
            
        try:
            import subprocess
            subprocess.run([
                'ffmpeg', '-y', '-i', self.video_path,
                '-ss', '00:00:00', '-frames:v', '1', temp_img
            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            if os.path.exists(temp_img):
                pixmap = QPixmap(temp_img)
                size = self.video_widget.size()
                scaled = pixmap.scaled(size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                self.fallback_image_label.setPixmap(scaled)
            else:
                self.fallback_image_label.setText("视频预览不可用")
            self.fallback_image_label.setVisible(True)
            self.fallback_image_label.raise_()
            self.video_widget.setVisible(False)
        except Exception as e:
            logger.error(f"Fallback frame extract failed: {e}")
            self.fallback_image_label.setText("视频预览不可用")
            self.fallback_image_label.setVisible(True)
            self.fallback_image_label.raise_()
            self.video_widget.setVisible(False)
        finally:
            try: 
                if os.path.exists(temp_img):
                    os.remove(temp_img)
            except Exception as e: 
                logger.debug(f"无法删除临时文件 {temp_img}: {e}")
                pass

    def _update_timeline_duration(self):
        """Update timeline duration from media player if loaded"""
        duration_ms = self.media_player.duration()
        if duration_ms > 0:
            self.timeline.set_duration(duration_ms / 1000.0)

    def _check_playback_and_fallback(self):
        """Choose playback backend: QMediaPlayer, VLC, or OpenCV"""
        if self.media_player and self.media_player.isVideoAvailable():
            # use QMediaPlayer
            self.use_vlc_playback = False
            return
            
        # 检查 VLC 是否可用
        if not vlc_available:
            logger.warning("VLC 不可用，直接使用备用播放方式")
            self.use_cv_playback = True
            self._init_cv_playback()
            self._media_fallback()
            return
            
        # try VLC playback
        try:
            self._init_vlc_playback()
            # if VLC media length available, choose it
            if hasattr(self, 'vlc_player') and self.vlc_player and self.vlc_player.get_length() > 0:
                self.use_vlc_playback = True
                return
        except Exception as e:
            logger.warning(f"VLC init failed: {e}")
            
        # fallback to OpenCV
        self.use_cv_playback = True
        try:
            self._init_cv_playback()
        except Exception as e:
            logger.error(f"OpenCV 初始化失败: {e}")
            self.status_bar.setText("无法初始化视频播放")
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
        self.play_action.setText("Play")
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
        """Override resize to maintain video aspect ratio"""
        super().resizeEvent(event)
        if hasattr(self, 'video_aspect_ratio') and self.video_aspect_ratio:
            w = self.video_stack.width()
            h = int(w / self.video_aspect_ratio)
            # enforce width; height auto adjusted by layout
            self.video_widget.setFixedHeight(h)
            self.fallback_image_label.setFixedHeight(h)

    def _apply_aspect_ratio(self):
        """Apply fixed aspect ratio to video display area"""
        if hasattr(self, 'video_aspect_ratio') and self.video_aspect_ratio:
            w = self.video_stack.width()
            h = int(w / self.video_aspect_ratio)
            # enforce width; height auto adjusted by layout
            self.video_widget.setFixedHeight(h)
            self.fallback_image_label.setFixedHeight(h)

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
        elif hasattr(self, 'cv_duration') and self.use_cv_playback:
            position = self.current_position
            duration = getattr(self, 'cv_duration', 0)
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
            self.play_action.setText("Play")

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
                    self.play_action.setText("Pause")
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

# 添加类别名，使SubtitleEditor指向SubtitleEditor
SubtitleEditorWidget = SubtitleEditor  # 兼容性别名