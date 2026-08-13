import dataclasses
import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any, Dict

from PyQt5.QtCore import QSettings, QSize, QThread, QTimer, pyqtSignal
from PyQt5.QtGui import QCloseEvent, QKeySequence
from PyQt5.QtWidgets import (
    QAction,
    QApplication,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QStatusBar,
    QToolBar,
    QVBoxLayout,
)

from app.config import (
    TRANSLATION_PROVIDERS,
    WHISPER_MODELS,
    AppConfig,
    ConfigManager,
    get_config_manager,
)
from app.core.subtitle import SubtitleProcessor
from app.gui.export_dialog import ExportDialog
from app.gui.processing import ProcessingWidget
from app.gui.subtitle_editor import SubtitleEditorWidget
from app.gui.video_export_thread import VideoExportWorker
from app.gui.video_import import VideoImportWidget
from app.resources.icons import IconManager
from app.resources.styles import StyleManager
from app.utils.checkpoint import CheckpointManager
from app.utils.exception_handler import ExceptionHandler, exception_handler
from app.utils.temp_files import TempFileManager


class WorkflowController:
    """工作流控制器，管理页面间的数据传递和状态转换"""
    
    def __init__(self, parent):
        self.parent = parent
        self.data = {}  # 存储工作流程中的数据
    
    def set_data(self, key: str, value: Any):
        """设置工作流数据"""
        self.data[key] = value
    
    def get_data(self, key: str) -> Any:
        """获取工作流数据"""
        return self.data.get(key)
    
    def clear_data(self):
        """清除所有工作流数据"""
        self.data.clear()
    
    def go_to_import(self):
        """转到导入页面"""
        self.parent.stacked_widget.setCurrentIndex(0)
    
    def go_to_processing(self):
        """转到处理页面"""
        self.parent.stacked_widget.setCurrentIndex(1)
    
    def go_to_editor(self):
        """转到编辑页面"""
        self.parent.stacked_widget.setCurrentIndex(2)

class SettingsDialog(QDialog):
    """Dialog for application settings: whisper model, translation provider, API key"""
    def __init__(self, config_manager: ConfigManager, config: AppConfig, parent=None):
        super().__init__(parent)
        self.setWindowTitle("设置")
        self.setMinimumWidth(520)
        self.config_manager = config_manager
        self.config = config
        self._current_provider = ""
        self._api_key_drafts = {}
        self._initial_api_keys = {}
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(16)

        title = QLabel("应用设置")
        title.setProperty("heading", True)
        title.setAccessibleName("应用设置")
        layout.addWidget(title)

        description = QLabel("调整识别模型、翻译服务和界面外观。密钥只保存到系统钥匙串。")
        description.setWordWrap(True)
        description.setProperty("muted", True)
        layout.addWidget(description)

        general_group = QGroupBox("处理与外观")
        form = QFormLayout(general_group)
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(12)
        # Whisper model
        self.model_combo = QComboBox()
        for model in WHISPER_MODELS:
            self.model_combo.addItem(model)
        self.model_combo.setCurrentText(self.config.get('whisper_model', 'base'))
        self.model_combo.setAccessibleName("Whisper 模型")
        self.model_combo.setToolTip("模型越大通常越准确，但占用的内存和处理时间也越多")
        form.addRow("Whisper 模型：", self.model_combo)
        # Translation provider
        self.provider_combo = QComboBox()
        for prov in TRANSLATION_PROVIDERS:
            self.provider_combo.addItem(prov)
        self.provider_combo.setCurrentText(self.config.get('translation_provider', 'OpenAI'))
        self.provider_combo.setAccessibleName("翻译提供商")
        form.addRow("翻译提供商：", self.provider_combo)
        # Theme
        self.theme_combo = QComboBox()
        self.theme_combo.addItem("跟随系统", "system")
        self.theme_combo.addItem("浅色", "light")
        self.theme_combo.addItem("深色", "dark")
        current_theme = str(self.config.get("theme", "system")).lower()
        theme_index = self.theme_combo.findData(current_theme)
        self.theme_combo.setCurrentIndex(theme_index if theme_index >= 0 else 0)
        self.theme_combo.setAccessibleName("界面主题")
        form.addRow("界面主题：", self.theme_combo)
        layout.addWidget(general_group)

        security_group = QGroupBox("翻译凭据")
        security_form = QFormLayout(security_group)
        security_form.setHorizontalSpacing(16)
        # API key
        api_row = QHBoxLayout()
        self.api_edit = QLineEdit()
        self.api_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_edit.setAccessibleName("翻译服务 API 密钥")
        self.api_edit.setPlaceholderText("安全保存到系统钥匙串")
        self.reveal_api_btn = QPushButton("显示")
        self.reveal_api_btn.setCheckable(True)
        self.reveal_api_btn.setFixedWidth(64)
        self.reveal_api_btn.toggled.connect(
            lambda shown: self.api_edit.setEchoMode(
                QLineEdit.EchoMode.Normal if shown else QLineEdit.EchoMode.Password
            )
        )
        self.reveal_api_btn.toggled.connect(
            lambda shown: self.reveal_api_btn.setText("隐藏" if shown else "显示")
        )
        self._current_provider = self.provider_combo.currentText()
        current_key = self._load_provider_key(self._current_provider)
        self.api_edit.setText(current_key)
        api_row.addWidget(self.api_edit)
        api_row.addWidget(self.reveal_api_btn)
        security_form.addRow("API 密钥：", api_row)
        # Update API key when provider changes
        self.provider_combo.currentTextChanged.connect(self._on_provider_changed)
        layout.addWidget(security_group)
        layout.addStretch(1)
        # Buttons
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _load_provider_key(self, provider: str) -> str:
        provider = provider.strip().lower()
        if provider not in self._initial_api_keys:
            value = self.config_manager.get_api_key(provider)
            self._initial_api_keys[provider] = value
            self._api_key_drafts[provider] = value
        return self._api_key_drafts[provider]

    def _on_provider_changed(self, provider: str) -> None:
        """Keep unsaved key edits per provider while navigating the dialog."""
        if self._current_provider:
            self._api_key_drafts[self._current_provider] = self.api_edit.text()
        self._current_provider = provider.strip().lower()
        self.api_edit.setText(self._load_provider_key(self._current_provider))

    def accept(self):
        # Save whisper model and translation provider
        self.config['whisper_model'] = self.model_combo.currentText()
        prov = self.provider_combo.currentText().strip().lower()
        self.config['translation_provider'] = prov
        self.config['theme'] = self.theme_combo.currentData()
        self._api_key_drafts[prov] = self.api_edit.text()

        transient_providers = []
        for provider, draft in self._api_key_drafts.items():
            key = draft.strip()
            if key == self._initial_api_keys.get(provider, ""):
                continue
            if not self.config_manager.set_api_key(provider, key, save_config=False):
                transient_providers.append(provider)
        self.config_manager.save_config(self.config)
        if transient_providers:
            QMessageBox.warning(
                self,
                "密钥未持久保存",
                "系统钥匙串当前不可用。以下服务的密钥仅在本次运行中有效，"
                "且不会写入配置文件：\n" + "、".join(transient_providers),
            )
        super().accept()

class MainWindow(QMainWindow):
    """应用主窗口"""

    BASE_WINDOW_TITLE = "视频翻译处理系统"
    
    progress_update = pyqtSignal(str, int)  # 进度更新信号 (状态信息, 进度百分比)
    
    def __init__(self, config: AppConfig, temp_manager: TempFileManager):
        super().__init__()
        self.config = config
        self.temp_manager = temp_manager
        self.workflow = WorkflowController(self)
        
        # 初始化异常处理器
        self.exception_handler = ExceptionHandler(self)
        # 设置为全局异常处理器
        from app.utils.exception_handler import set_global_exception_handler
        set_global_exception_handler(self.exception_handler)

        script_dir = os.path.dirname(os.path.abspath(__file__))  # 当前文件所在目录
        project_root = os.path.dirname(os.path.dirname(script_dir))  # 项目根目录
        icons_dir = os.path.join(project_root, "app", "resources", "icons")
        
        self.icon_manager = IconManager(icons_dir)
        self.style_manager = StyleManager()
        
        self.has_unsaved_changes = False
        self.current_video_path = None
        self.current_project_path = None
        self.current_subtitle_path = None
        # 兼容旧插件/测试；始终指向当前视频而不是项目文件。
        self.current_file_path = None
        self._export_thread = None
        self._export_worker = None
        self._export_dialog = None
        self._close_after_export_cancel = False
        self._close_after_processing_cancel = False
        self._processing_close_hooked = False
        self._themed_actions = []
        
        self.setup_ui()
        self.setup_menu()
        self.setup_toolbar()
        self.setup_statusbar()
        self.setup_connections()
        self.apply_styles()
        
        # 设置窗口属性
        self._update_window_title()
        self.resize(1200, 800)
        self.setMinimumSize(800, 600)
        
        # 恢复窗口状态
        self.restore_settings()
    
    def setup_ui(self):
        """设置用户界面"""
        self.stacked_widget = QStackedWidget()
        self.setCentralWidget(self.stacked_widget)
        
        # 创建各个工作流页面
        self.video_import_widget = VideoImportWidget(self.config)
        self.processing_widget = ProcessingWidget(self.config)
        
        # 初始化字幕编辑器：先传入空路径和新的SubtitleProcessor实例
        subtitle_processor = SubtitleProcessor()
        self.subtitle_editor_widget = SubtitleEditorWidget("", subtitle_processor)
        
        # 添加到堆叠窗口部件
        self.stacked_widget.addWidget(self.video_import_widget)
        self.stacked_widget.addWidget(self.processing_widget)
        self.stacked_widget.addWidget(self.subtitle_editor_widget)
        
        # 默认显示导入页面
        self.stacked_widget.setCurrentIndex(0)
    
    def setup_menu(self):
        """设置菜单栏"""
        menubar = self.menuBar()
        
        # 文件菜单
        file_menu = menubar.addMenu("文件(&F)")
        
        self.open_action = QAction(self.icon_manager.get_icon("open"), "打开视频(&O)", self)
        self.open_action.setShortcut(QKeySequence.StandardKey.Open)
        self.open_action.triggered.connect(self.open_video_dialog)
        file_menu.addAction(self.open_action)
        # 打开项目文件(.vtp)
        self.open_project_action = QAction(self.icon_manager.get_icon("open"), "打开项目文件(&P)", self)
        self.open_project_action.setShortcut("Ctrl+Shift+O")
        self.open_project_action.triggered.connect(self.open_project_file)
        file_menu.addAction(self.open_project_action)

        self.import_subtitle_action = QAction(
            self.icon_manager.get_icon("open"), "导入字幕(&I)...", self
        )
        self.import_subtitle_action.setShortcut("Ctrl+I")
        self.import_subtitle_action.setToolTip(
            "为当前视频导入 SRT、VTT、ASS/SSA、SUB 或 SBV"
        )
        self.import_subtitle_action.triggered.connect(
            lambda _checked=False: self.import_subtitle_file()
        )
        file_menu.addAction(self.import_subtitle_action)
        
        # 最近文件子菜单
        self.recent_menu = QMenu("最近文件(&R)", self)
        file_menu.addMenu(self.recent_menu)
        self.update_recent_menu()
        
        file_menu.addSeparator()
        
        # Save & Save As - disabled until subtitles are ready
        self.save_action = QAction(self.icon_manager.get_icon("save"), "保存项目(&S)", self)
        self.save_action.setShortcut(QKeySequence.StandardKey.Save)
        self.save_action.triggered.connect(self.save_project)
        self.save_action.setEnabled(False)
        file_menu.addAction(self.save_action)
        
        self.save_as_action = QAction("另存为(&A)...", self)
        self.save_as_action.setShortcut(QKeySequence.StandardKey.SaveAs)
        self.save_as_action.triggered.connect(self.save_project_as)
        self.save_as_action.setEnabled(False)
        file_menu.addAction(self.save_as_action)
        
        file_menu.addSeparator()
        
        # Export action
        self.export_action = QAction(self.icon_manager.get_icon("export"), "导出(&E)...", self)
        self.export_action.setShortcut("Ctrl+E")
        self.export_action.triggered.connect(self.show_export_dialog)
        self.export_action.setEnabled(False)
        file_menu.addAction(self.export_action)
        
        file_menu.addSeparator()
        
        exit_action = QAction("退出(&Q)", self)
        exit_action.setShortcut(QKeySequence.StandardKey.Quit)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        # 编辑菜单
        edit_menu = menubar.addMenu("编辑(&E)")
        
        # Undo/Redo actions
        self.undo_action = QAction(self.icon_manager.get_icon("undo"), "撤销(&U)", self)
        self.undo_action.setShortcut(QKeySequence.StandardKey.Undo)
        self.undo_action.triggered.connect(self.undo)
        self.undo_action.setEnabled(False)
        edit_menu.addAction(self.undo_action)
        
        self.redo_action = QAction(self.icon_manager.get_icon("redo"), "重做(&R)", self)
        self.redo_action.setShortcut(QKeySequence.StandardKey.Redo)
        self.redo_action.triggered.connect(self.redo)
        self.redo_action.setEnabled(False)
        edit_menu.addAction(self.redo_action)
        
        settings_action = QAction(self.icon_manager.get_icon("settings"), "设置(&S)...", self)
        settings_action.triggered.connect(self.show_settings)
        edit_menu.addAction(settings_action)
        self.settings_action = settings_action

        self._themed_actions = [
            (self.open_action, "open"),
            (self.open_project_action, "open"),
            (self.import_subtitle_action, "open"),
            (self.save_action, "save"),
            (self.export_action, "export"),
            (self.undo_action, "undo"),
            (self.redo_action, "redo"),
            (self.settings_action, "settings"),
        ]
        
        # 帮助菜单
        help_menu = menubar.addMenu("帮助(&H)")
        
        about_action = QAction("关于(&A)", self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)
    
    def setup_toolbar(self):
        """设置工具栏"""
        toolbar = QToolBar("主工具栏", self)
        toolbar.setObjectName("mainToolbar")
        toolbar.setIconSize(QSize(24, 24))
        self.addToolBar(toolbar)
        
        # Toolbar actions: use menu action instances to keep enabled state
        toolbar.addAction(self.open_action)
        toolbar.addAction(self.import_subtitle_action)
        toolbar.addAction(self.save_action)
        toolbar.addAction(self.export_action)
        
        toolbar.addSeparator()
        
        toolbar.addAction(self.undo_action)
        toolbar.addAction(self.redo_action)
    
    def setup_statusbar(self):
        """设置状态栏"""
        self.statusbar = QStatusBar(self)
        self.setStatusBar(self.statusbar)
        
        self.status_label = QLabel("就绪")
        self.statusbar.addWidget(self.status_label, 1)
        
        self.progress_label = QLabel()
        self.statusbar.addPermanentWidget(self.progress_label)

        self.cancel_export_button = QPushButton("取消导出")
        self.cancel_export_button.setAccessibleName("取消正在进行的导出")
        self.cancel_export_button.clicked.connect(self.cancel_export)
        self.cancel_export_button.setVisible(False)
        self.statusbar.addPermanentWidget(self.cancel_export_button)
    
    def setup_connections(self):
        """设置信号和槽连接"""
        # 导入页面信号
        self.video_import_widget.continue_signal.connect(self.start_processing)
        self.video_import_widget.video_info_loaded.connect(
            lambda info: self.workflow.set_data("video_info", info)
        )
        
        # 处理页面信号
        self.processing_widget.processing_completed.connect(self.processing_complete)
        self.processing_widget.processing_error.connect(self.processing_error)
        self.processing_widget.processing_cancelled.connect(self.processing_cancelled)
        
        # 编辑页面信号，使用 segmentsChanged 信号标记未保存更改
        self.subtitle_editor_widget.segmentsChanged.connect(self.mark_unsaved_changes)
        self.subtitle_editor_widget.importSubtitleRequested.connect(
            self.import_subtitle_file
        )
        self.subtitle_editor_widget.undo_stack.canUndoChanged.connect(
            self._update_undo_action
        )
        self.subtitle_editor_widget.undo_stack.canRedoChanged.connect(
            self._update_redo_action
        )
        
        # 进度更新信号
        self.progress_update.connect(self.update_progress)
        
        # When page changes, update action states
        self.stacked_widget.currentChanged.connect(self.update_action_states)
    
    def apply_styles(self):
        """应用应用程序样式"""
        requested_theme = self.config.get("theme", "system")
        resolved_theme = self.style_manager.apply_theme(requested_theme, self)
        self.icon_manager.set_theme(resolved_theme)
        for action, icon_name in self._themed_actions:
            action.setIcon(self.icon_manager.get_icon(icon_name))

    def _update_window_title(self) -> None:
        """Derive the title from state so the unsaved marker cannot accumulate."""
        title = self.BASE_WINDOW_TITLE
        if self.current_video_path:
            title += f" - {os.path.basename(self.current_video_path)}"
        if self.current_project_path:
            title += f" [项目: {os.path.basename(self.current_project_path)}]"
        if self.has_unsaved_changes:
            title += " *"
        self.setWindowTitle(title)

    def _set_unsaved_changes(self, changed: bool) -> None:
        self.has_unsaved_changes = bool(changed)
        self._update_window_title()
    
    def update_recent_menu(self):
        """更新最近文件菜单"""
        self.recent_menu.clear()
        recent_files = self.config.get("recent_files", [])
        
        if not recent_files:
            no_files_action = QAction("没有最近文件", self)
            no_files_action.setEnabled(False)
            self.recent_menu.addAction(no_files_action)
            return
        
        for file_path in recent_files:
            if os.path.exists(file_path):
                action = QAction(os.path.basename(file_path), self)
                action.setData(file_path)
                action.setToolTip(file_path)
                action.triggered.connect(self.open_recent_file)
                self.recent_menu.addAction(action)
    
    def open_video_dialog(self):
        """打开视频文件对话框"""
        file_filter = "视频文件 ({});;所有文件 (*)".format(
            " ".join(f"*.{ext}" for ext in self.config.get("supported_video_formats", ["mp4", "mkv"])))
        
        filepath, _ = QFileDialog.getOpenFileName(
            self, "打开视频文件", 
            self.config.get("last_directory", os.path.expanduser("~")),
            file_filter
        )
        
        if filepath:
            self.open_video(filepath)

    @staticmethod
    def _subtitle_file_filter() -> str:
        return (
            "字幕文件 (*.srt *.vtt *.ass *.ssa *.sub *.sbv);;"
            "SubRip (*.srt);;WebVTT (*.vtt);;ASS/SSA (*.ass *.ssa);;"
            "MicroDVD (*.sub);;YouTube SBV (*.sbv)"
        )

    def _choose_video_for_subtitle_import(self, start_directory: str) -> str:
        """Ask for the one video that gives an imported subtitle its timeline."""
        file_filter = "视频文件 ({});;所有文件 (*)".format(
            " ".join(
                f"*.{ext}"
                for ext in self.config.get(
                    "supported_video_formats", ["mp4", "mkv"]
                )
            )
        )
        filepath, _ = QFileDialog.getOpenFileName(
            self, "先选择字幕对应的视频", start_directory, file_filter
        )
        return filepath

    def import_subtitle_file(
        self,
        filepath: str = None,
        *,
        video_filepath: str = None,
    ) -> bool:
        """Import an existing subtitle into the editor without transcription.

        Parsing happens in an isolated processor first. Existing editor data is
        replaced only after every prerequisite succeeds, so malformed input or
        cancelled dialogs cannot corrupt the current session.
        """
        if self.has_unsaved_changes and not self.confirm_discard_changes():
            return False

        start_directory = self.config.get(
            "last_directory", os.path.expanduser("~")
        )
        if not filepath:
            filepath, _ = QFileDialog.getOpenFileName(
                self,
                "导入字幕文件",
                start_directory,
                self._subtitle_file_filter(),
            )
        if not filepath:
            return False

        subtitle_path = os.path.abspath(os.path.expanduser(filepath))
        suffix = Path(subtitle_path).suffix.lower()
        if suffix not in SubtitleProcessor.SUPPORTED_FORMATS.values():
            QMessageBox.warning(
                self,
                "导入失败",
                "不支持该字幕格式。请选择 SRT、VTT、ASS/SSA、"
                "MicroDVD SUB 或 YouTube SBV。",
            )
            return False

        video_path = (
            video_filepath
            or self.workflow.get_data("video_path")
            or self.current_video_path
            or getattr(self.video_import_widget, "video_path", None)
        )
        if not video_path or not os.path.isfile(video_path):
            video_path = self._choose_video_for_subtitle_import(
                os.path.dirname(subtitle_path) or start_directory
            )
        if not video_path:
            self.status_label.setText("已取消字幕导入")
            return False
        video_path = os.path.abspath(os.path.expanduser(video_path))
        if not os.path.isfile(video_path):
            QMessageBox.warning(
                self,
                "缺少视频",
                "请先选择字幕对应的有效视频文件，再重试导入。",
            )
            return False

        try:
            staged_processor = SubtitleProcessor()
            staged_segments = staged_processor.load_from_file(subtitle_path)
            if not staged_segments:
                raise ValueError("字幕文件中没有可用片段")
            staged_data = [dataclasses.asdict(segment) for segment in staged_segments]
        except Exception as exc:
            logging.warning("字幕导入失败: %s", exc)
            QMessageBox.warning(
                self, "导入失败", f"无法解析字幕文件：\n{exc}"
            )
            return False

        source_language = (
            self.workflow.get_data("source_language")
            or self.video_import_widget.get_source_language()
            or self.config.get("default_source_language", "auto")
        )
        target_language = (
            self.workflow.get_data("target_language")
            or self.video_import_widget.get_target_language()
            or self.config.get("default_target_language", "zh-CN")
        )
        result_data = {
            "video_path": video_path,
            "segments": staged_data,
            "subtitle_source_path": subtitle_path,
            "is_subtitle_import": True,
        }

        video_info = self.workflow.get_data("video_info")
        import_widget_video = getattr(self.video_import_widget, "video_path", None)
        if not isinstance(video_info, dict) or (
            import_widget_video
            and os.path.normcase(os.path.abspath(import_widget_video))
            != os.path.normcase(video_path)
        ):
            video_info = None
        if video_info is None and (
            import_widget_video
            and os.path.normcase(os.path.abspath(import_widget_video))
            == os.path.normcase(video_path)
        ):
            candidate = getattr(self.video_import_widget, "video_info", None)
            video_info = candidate if isinstance(candidate, dict) else None

        self.workflow.clear_data()
        self.workflow.set_data("video_path", video_path)
        self.workflow.set_data("source_language", source_language)
        self.workflow.set_data("target_language", target_language)
        self.workflow.set_data("processing_results", result_data)
        if video_info:
            self.workflow.set_data("video_info", video_info)
        self.current_video_path = video_path
        self.current_file_path = video_path
        self.current_project_path = None
        self.current_subtitle_path = subtitle_path
        self.subtitle_editor_widget.load_data(video_path, result_data)
        self.subtitle_editor_widget.clear_undo_history()
        timeline_duration = (
            float(video_info.get("duration", 0) or 0) if video_info else 0.0
        )
        if timeline_duration <= 0:
            timeline_duration = max(
                (segment.end_time for segment in staged_segments), default=0.0
            )
        if timeline_duration > 0:
            self.subtitle_editor_widget.timeline.set_duration(timeline_duration)
        self.workflow.go_to_editor()
        self._set_unsaved_changes(True)
        self._sync_undo_redo_actions()
        self.save_action.setEnabled(True)
        self.save_as_action.setEnabled(True)
        self.export_action.setEnabled(True)
        self.status_label.setText(
            f"已导入字幕: {os.path.basename(subtitle_path)}"
        )

        subtitle_directory = os.path.dirname(subtitle_path)
        self.config["last_directory"] = subtitle_directory
        config_manager = get_config_manager()
        config_manager.config["last_directory"] = subtitle_directory
        config_manager.add_recent_file(subtitle_path)
        self.config.recent_files = list(config_manager.config.recent_files)
        self.update_recent_menu()
        return True
    
    @exception_handler("打开视频文件")
    def open_video(self, filepath: str):
        """打开视频文件
        
        Args:
            filepath: 视频文件路径
        """
        if self.has_unsaved_changes and not self.confirm_discard_changes():
            return

        filepath = os.path.abspath(os.path.expanduser(filepath))
        # 验证文件是否存在
        if not os.path.exists(filepath):
            logging.error(f"文件不存在: {filepath}")
            self.exception_handler.handle_exception(
                FileNotFoundError(f"文件不存在: {filepath}"), 
                "打开视频文件"
            )
            return
            
        # 验证文件格式
        _, ext = os.path.splitext(filepath)
        ext = ext[1:].lower() if ext else ""
        
        if ext not in self.config.get("supported_video_formats", ["mp4", "mkv"]):
            logging.warning(f"不支持的文件格式: {ext}")
            result = QMessageBox.warning(
                self, 
                "不支持的格式", 
                f"文件格式 '{ext}' 可能不受支持。是否仍要尝试打开？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if result != QMessageBox.StandardButton.Yes:
                return
        
        # 保存最后使用的目录
        self.config["last_directory"] = os.path.dirname(filepath)
        
        # 添加到最近文件列表
        config_manager = get_config_manager()
        config_manager.add_recent_file(filepath)
        self.config.recent_files = list(config_manager.config.recent_files)
        self.update_recent_menu()
        
        # 清除旧数据
        self.workflow.clear_data()
        self.subtitle_editor_widget.clear_undo_history()
        
        # 设置新文件路径
        self.current_video_path = filepath
        self.current_file_path = filepath
        self.current_project_path = None
        self.current_subtitle_path = None
        self._set_unsaved_changes(False)
        
        # 显示临时进度信息
        self.status_label.setText(f"正在加载: {os.path.basename(filepath)}...")
        QApplication.processEvents()  # 确保UI更新
        
        # 设置工作流数据并跳转到导入页面
        self.workflow.set_data("video_path", filepath)
        
        # 检查是否有断点续传数据
        checkpoint_manager = CheckpointManager()
        if checkpoint_manager.can_resume(filepath):
            recovery_info = checkpoint_manager.get_recovery_info(filepath)
            if recovery_info:
                # 显示断点续传对话框
                result = self.show_resume_dialog(recovery_info)
                if result == QMessageBox.StandardButton.Yes:
                    # 用户选择继续处理，直接跳转到处理页面
                    self.workflow.go_to_processing()
                    self.start_processing_with_resume(filepath)
                    return
                elif result == QMessageBox.StandardButton.No:
                    # 用户选择重新开始，清除检查点
                    checkpoint_manager.clear_checkpoint(filepath)
        
        # 导入页面负责唯一一次媒体探测与缩略图生成。旧代码
        # 在此先 ffprobe，set_video_path 中又 ffprobe 和 FFmpeg，会将
        # 同一文件重复探测并加倍打开时的主线程停顿。
        self.video_import_widget.set_video_path(filepath)
        self.workflow.go_to_import()
        
        # 重置未保存状态
        self._set_unsaved_changes(False)
        self.status_label.setText(f"已加载: {os.path.basename(filepath)}")
    
    def open_recent_file(self):
        """打开最近的文件"""
        action = self.sender()
        if action:
            filepath = action.data()
            if os.path.exists(filepath):
                suffix = Path(filepath).suffix.lower()
                if suffix == ".vtp":
                    self.open_project_file(filepath)
                elif suffix in SubtitleProcessor.SUPPORTED_FORMATS.values():
                    self.import_subtitle_file(filepath)
                else:
                    self.open_video(filepath)
            else:
                QMessageBox.warning(self, "文件不存在", f"文件 {filepath} 不存在或已被移动。")
                
                # 从最近文件列表中移除
                config_manager = get_config_manager()
                config = config_manager.config
                if filepath in config.recent_files:
                    config.recent_files.remove(filepath)
                    config_manager.save_config()
                    self.config.recent_files = list(config.recent_files)
                    self.update_recent_menu()
    
    def save_project(self, save_path: str = None):
        """保存项目"""
        # Determine save path: use provided save_path or default based on video path
        video_path = self.workflow.get_data('video_path')
        results = self.workflow.get_data('processing_results')
        if not video_path and isinstance(results, dict):
            video_path = results.get('video_path')
        if not video_path:
            QMessageBox.warning(self, "保存失败", "未加载任何项目，无法保存。")
            return False
        # Ensure in editor page
        if self.stacked_widget.currentIndex() != 2:
            QMessageBox.information(self, "保存失败", "请在字幕编辑页面执行保存操作。")
            return False
        subtitle_data = self.subtitle_editor_widget.get_processed_segments()
        if not subtitle_data:
            QMessageBox.warning(self, "保存失败", "当前没有字幕数据可保存。")
            return False
        # If no save_path given, prefer existing project path, else video base path
        if not save_path:
            if self.current_project_path:
                save_path = self.current_project_path
            else:
                save_path = os.path.splitext(video_path)[0] + ".vtp"
        # Write project file
        try:
            save_path = os.path.abspath(os.path.expanduser(save_path))
            directory = os.path.dirname(save_path)
            video_path = os.path.abspath(os.path.expanduser(video_path))
            try:
                relative_video_path = os.path.relpath(video_path, directory)
            except ValueError:  # Different Windows drives cannot be relative.
                relative_video_path = None
            project_data = {
                'schema': 'videotranslator.project',
                'version': 2,
                'video_path': video_path,
                'video_path_relative': relative_video_path,
                'source_language': self.workflow.get_data('source_language'),
                'target_language': self.workflow.get_data('target_language'),
                'segments': [dataclasses.asdict(seg) for seg in subtitle_data],
            }
            os.makedirs(directory, exist_ok=True)
            temp_name = None
            try:
                with tempfile.NamedTemporaryFile(
                    mode='w', encoding='utf-8', dir=directory,
                    prefix=f".{os.path.basename(save_path)}.", suffix='.tmp', delete=False
                ) as f:
                    temp_name = f.name
                    json.dump(project_data, f, ensure_ascii=False, indent=2)
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(temp_name, save_path)
            finally:
                if temp_name and os.path.exists(temp_name):
                    os.unlink(temp_name)
            self.current_video_path = video_path
            self.current_file_path = video_path
            self.current_project_path = save_path
            self._set_unsaved_changes(False)
            self.status_label.setText(f"项目已保存: {os.path.basename(save_path)}")
            return True
        except Exception as e:
            logging.error(f"保存项目失败: {str(e)}")
            QMessageBox.warning(self, "保存失败", f"保存项目时发生错误:\n{str(e)}")
            return False

    def save_project_as(self):
        """另存为项目"""
        # 默认路径：优先使用已打开的项目文件路径，否则使用视频基础名
        default_path = ''
        if self.current_project_path:
            default_path = self.current_project_path
        else:
            video_path = self.workflow.get_data('video_path') or (self.workflow.get_data('processing_results') or {}).get('video_path')
            if video_path:
                default_path = os.path.splitext(video_path)[0] + ".vtp"
        filepath, _ = QFileDialog.getSaveFileName(
            self, "保存项目", default_path, "VideoTranslator 项目 (*.vtp)"
        )
        if not filepath:
            return False
        if not filepath.lower().endswith('.vtp'):
            filepath += '.vtp'
        # Save to specified path
        return self.save_project(filepath)
    
    def show_export_dialog(self):
        """显示导出对话框"""
        if self.is_exporting:
            self.status_label.setText("已有导出任务正在进行")
            return
        # Determine video path from workflow or processing results
        video_path = self.workflow.get_data('video_path')
        results = self.workflow.get_data('processing_results')
        if not video_path and isinstance(results, dict):
            video_path = results.get('video_path')
        if not video_path:
            QMessageBox.warning(self, "导出失败", "未找到视频文件路径，无法导出。")
            return
        self.current_video_path = video_path
        self.current_file_path = video_path
        if (self.stacked_widget.currentIndex() != 2):  # 不在编辑页面
            QMessageBox.information(self, "无法导出", "请先完成字幕编辑后再导出。")
            return
            
        dialog = ExportDialog(self, self.config, video_path)
        if dialog.exec():
            subtitle_data = self.subtitle_editor_widget.get_processed_segments()
            export_options = dialog.get_export_options()
            export_options["subtitle_data"] = [
                dataclasses.asdict(segment) for segment in subtitle_data
            ]
            export_options["video_path"] = video_path
            export_options["target_language"] = self.workflow.get_data(
                "target_language"
            ) or self.config.get("target_language", "und")
            self._start_export(export_options, dialog)

    @property
    def is_exporting(self) -> bool:
        """Whether an export worker thread is still active."""
        # Keep the task busy until the GUI has handled thread.finished;
        # otherwise a second export could replace these object references in
        # the small interval after QThread stops but before cleanup runs.
        return self._export_thread is not None

    def _start_export(self, export_options, dialog=None):
        """Start one guarded background export."""
        if self.is_exporting:
            self.status_label.setText("已有导出任务正在进行")
            return False

        self._export_dialog = dialog
        self._export_thread = QThread(self)
        self._export_worker = VideoExportWorker(export_options)
        self._export_worker.moveToThread(self._export_thread)

        self._export_thread.started.connect(self._export_worker.run)
        self._export_worker.progress.connect(self._on_export_progress)
        self._export_worker.succeeded.connect(self._on_export_succeeded)
        self._export_worker.failed.connect(self._on_export_failed)
        self._export_worker.cancelled.connect(self._on_export_cancelled)
        self._export_worker.finished.connect(self._export_thread.quit)
        self._export_worker.finished.connect(self._export_worker.deleteLater)
        self._export_thread.finished.connect(self._on_export_thread_finished)
        self._export_thread.finished.connect(self._export_thread.deleteLater)

        self.status_label.setText("正在准备导出…")
        self.progress_label.setText("0%")
        self.cancel_export_button.setEnabled(True)
        self.cancel_export_button.setVisible(True)
        self.export_action.setEnabled(False)
        self._export_thread.start()
        return True

    def _on_export_progress(self, percent, message):
        self.status_label.setText(message)
        self.progress_label.setText(f"{max(0, min(100, percent))}%")

    def _on_export_succeeded(self, output_path, message):
        self.status_label.setText(f"导出完成: {os.path.basename(output_path)}")
        self.progress_label.setText("100%")
        if not self._close_after_export_cancel and self._export_dialog is not None:
            self._export_dialog.show_export_result(True, message, output_path)

    def _on_export_failed(self, message):
        logging.error("导出失败: %s", message)
        self.status_label.setText("导出失败")
        if not self._close_after_export_cancel and self._export_dialog is not None:
            self._export_dialog.show_export_result(
                False, f"导出时发生错误:\n{message}"
            )

    def _on_export_cancelled(self):
        self.status_label.setText("导出已取消；目标文件未被更改")

    def _on_export_thread_finished(self):
        should_close = self._close_after_export_cancel
        self.cancel_export_button.setVisible(False)
        self.progress_label.clear()
        self._export_worker = None
        self._export_thread = None
        self._export_dialog = None
        self._close_after_export_cancel = should_close
        self.update_action_states(self.stacked_widget.currentIndex())
        if should_close:
            QTimer.singleShot(0, self.close)

    def cancel_export(self):
        """Cooperatively cancel the active worker and its FFmpeg process."""
        if self._export_worker is None or not self.is_exporting:
            return
        self.cancel_export_button.setEnabled(False)
        self.status_label.setText("正在安全取消导出…")
        # Direct call is intentional: cancel() is thread-safe and can terminate
        # a child process while the worker event loop is occupied by run().
        self._export_worker.cancel()
    
    def _export_subtitle_file(self, processor, export_options, dialog):
        """Compatibility entry point; export still runs in the worker thread."""
        if "subtitle_data" not in export_options:
            export_options = dict(export_options)
            export_options["subtitle_data"] = [
                dataclasses.asdict(segment) for segment in processor.segments
            ]
        return self._start_export(export_options, dialog)
    
    def _export_video_with_subtitles(self, processor, export_options, dialog):
        """Compatibility entry point; video export runs in the worker thread."""
        if "subtitle_data" not in export_options:
            export_options = dict(export_options)
            export_options["subtitle_data"] = [
                dataclasses.asdict(segment) for segment in processor.segments
            ]
        return self._start_export(export_options, dialog)
    
    def start_processing(self):
        """开始处理视频"""
        # 获取导入页面设置
        video_path = self.workflow.get_data("video_path")
        # 如果 workflow 未设置，尝试从 import widget 获取
        if not video_path and hasattr(self.video_import_widget, 'video_path'):
            video_path = self.video_import_widget.video_path
        # 验证视频路径
        if not video_path:
            QMessageBox.warning(self, "错误", "未选择视频文件，请先导入视频。")
            return
        source_lang = self.video_import_widget.get_source_language()
        target_lang = self.video_import_widget.get_target_language()

        # 保存到工作流数据
        self.workflow.set_data("source_language", source_lang)
        self.workflow.set_data("target_language", target_lang)
        
        # Ensure current_file_path and workflow video_path are set (import widget selection)
        self.current_video_path = video_path
        self.current_file_path = video_path
        self.workflow.set_data('video_path', video_path)
        # 转到处理页面
        self.workflow.go_to_processing()
        
        # 开始处理
        self.processing_widget.start_processing(
            video_path=video_path,
            source_language=source_lang,
            target_language=target_lang,
            whisper_model=self.config.get("whisper_model", "base"),
            translation_provider=self.config.get("translation_provider", "OpenAI")
        )
    
    def processing_complete(self, result_data):
        """处理完成回调"""
        if self._close_after_processing_cancel:
            self.status_label.setText("处理已结束，正在退出…")
            self._finish_close_after_processing()
            return
        # 将结果保存到工作流
        self.workflow.set_data("processing_results", result_data)
        
        # 转到编辑器页面
        self.workflow.go_to_editor()
        
        # 加载数据到编辑器
        self.subtitle_editor_widget.load_data(
            self.current_video_path,
            result_data
        )
        self.mark_unsaved_changes()
        # 设置时间轴总时长，使用预加载的视频信息（避免播放器失败）
        video_info = self.workflow.get_data('video_info')
        if (video_info and 'duration' in video_info):
            self.subtitle_editor_widget.timeline.set_duration(video_info['duration'])
        
        self.status_label.setText("处理完成，请编辑字幕")
        # 切换到编辑后确保窗口可见并获取焦点
        self.subtitle_editor_widget.raise_()
        self.subtitle_editor_widget.activateWindow()
        self.raise_()
        self.activateWindow()
        
        # Enable save actions; undo/redo reflect the new clean history.
        self.save_action.setEnabled(True)
        self.save_as_action.setEnabled(True)
        self._sync_undo_redo_actions()
    
    def processing_error(self, error_message):
        """处理错误回调"""
        if self._close_after_processing_cancel:
            logging.info("关闭期间处理任务结束: %s", error_message)
            self._finish_close_after_processing()
            return
        QMessageBox.critical(self, "处理错误", f"处理视频时发生错误:\n{error_message}")
        self.workflow.go_to_import()
        self.status_label.setText("处理失败")

    def processing_cancelled(self):
        """主动取消不是故障；返回导入页并保留恢复点。"""
        if self._close_after_processing_cancel:
            self.status_label.setText("处理已安全停止，正在退出…")
            self._finish_close_after_processing()
            return
        self.workflow.go_to_import()
        self.status_label.setText("处理已取消，可稍后从恢复点继续")
    
    def update_progress(self, message, percentage):
        """更新进度信息"""
        self.progress_label.setText(f"{message} {percentage}%")
    
    def undo(self):
        """撤销操作"""
        if self.stacked_widget.currentIndex() == 2:  # 编辑页面
            self.subtitle_editor_widget.undo()
    
    def redo(self):
        """重做操作"""
        if self.stacked_widget.currentIndex() == 2:  # 编辑页面
            self.subtitle_editor_widget.redo()

    def _update_undo_action(self, can_undo: bool) -> None:
        """Mirror the editor history without enabling actions on other pages."""
        self.undo_action.setEnabled(
            self.stacked_widget.currentIndex() == 2 and bool(can_undo)
        )

    def _update_redo_action(self, can_redo: bool) -> None:
        """Mirror the editor history without enabling actions on other pages."""
        self.redo_action.setEnabled(
            self.stacked_widget.currentIndex() == 2 and bool(can_redo)
        )

    def _sync_undo_redo_actions(self) -> None:
        """Synchronize main-window actions with the shared subtitle stack."""
        stack = self.subtitle_editor_widget.undo_stack
        self._update_undo_action(stack.canUndo())
        self._update_redo_action(stack.canRedo())
    
    def mark_unsaved_changes(self):
        """标记有未保存的更改"""
        self._set_unsaved_changes(True)
    
    def confirm_discard_changes(self) -> bool:
        """确认是否放弃未保存的更改"""
        if not self.has_unsaved_changes:
            return True
            
        result = QMessageBox.question(
            self,
            "未保存的更改",
            "当前有未保存的更改，是否保存？",
            QMessageBox.StandardButton.Save | 
            QMessageBox.StandardButton.Discard | 
            QMessageBox.StandardButton.Cancel
        )
        
        if result == QMessageBox.StandardButton.Save:
            return self.save_project()
        elif result == QMessageBox.StandardButton.Discard:
            return True
        else:  # Cancel
            return False
    
    def show_settings(self):
        """显示设置对话框"""
        config_manager = get_config_manager()
        dialog = SettingsDialog(config_manager, self.config, self)
        if dialog.exec() == QDialog.Accepted:
            self.apply_styles()
    
    def show_about(self):
        """显示关于对话框"""
        QMessageBox.about(
            self,
            "关于视频翻译处理系统",
            f"视频翻译处理系统 v{self.config.get('app_version', '1.0.0')}\n\n"
            "一个用于视频翻译和字幕生成的工具。\n\n"
            "隐私优先的本地视频翻译与字幕工作台。"
        )
    
    def save_settings(self):
        """保存窗口状态和设置"""
        settings = QSettings("VideoTranslator", "VideoTranslator")
        settings.setValue("geometry", self.saveGeometry())
        settings.setValue("windowState", self.saveState())
    
    def restore_settings(self):
        """恢复窗口状态和设置"""
        settings = QSettings("VideoTranslator", "VideoTranslator")
        if settings.contains("geometry"):
            self.restoreGeometry(settings.value("geometry"))
        if settings.contains("windowState"):
            self.restoreState(settings.value("windowState"))

    def _processing_thread_is_running(self) -> bool:
        thread = getattr(self.processing_widget, "thread", None)
        if not isinstance(thread, QThread):
            return False
        try:
            return thread.isRunning()
        except RuntimeError:
            # The Python wrapper can briefly outlive the deleted Qt object.
            return False

    def _finish_close_after_processing(self) -> None:
        """Close only after the processing QThread has actually stopped."""
        if not self._close_after_processing_cancel:
            return
        thread = getattr(self.processing_widget, "thread", None)
        if self._processing_thread_is_running():
            if not self._processing_close_hooked:
                self._processing_close_hooked = True
                thread.finished.connect(self._finish_close_after_processing)
            return
        self._processing_close_hooked = False
        QTimer.singleShot(0, self.close)
    
    def closeEvent(self, event: QCloseEvent):
        """窗口关闭事件处理"""
        finishing_requested_close = (
            (self._close_after_export_cancel and not self.is_exporting)
            or (
                self._close_after_processing_cancel
                and not self.processing_widget.is_processing
                and not self._processing_thread_is_running()
            )
        )
        cancellation_in_progress = (
            (self._close_after_export_cancel and self.is_exporting)
            or (
                self._close_after_processing_cancel
                and (
                    self.processing_widget.is_processing
                    or self._processing_thread_is_running()
                )
            )
        )
        if cancellation_in_progress:
            event.ignore()
            return
        if (
            not finishing_requested_close
            and self.has_unsaved_changes
            and not self.confirm_discard_changes()
        ):
            event.ignore()
            return

        if not finishing_requested_close and self.processing_widget.is_processing:
            answer = QMessageBox.question(
                self, "处理仍在进行",
                "当前任务仍在处理。要安全取消并退出吗？恢复点会被保留。",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            self._close_after_processing_cancel = True
            self.processing_widget.cancel_processing()
            self._finish_close_after_processing()
            event.ignore()
            self.status_label.setText("正在安全停止任务，完成后将自动退出…")
            return

        if not finishing_requested_close and self.is_exporting:
            answer = QMessageBox.question(
                self,
                "导出仍在进行",
                "当前文件仍在导出。要安全取消导出并退出吗？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            self._close_after_export_cancel = True
            self.cancel_export()
            event.ignore()
            return

        self._close_after_export_cancel = False
        self._close_after_processing_cancel = False
        self._processing_close_hooked = False

        cleanup_player = getattr(self.subtitle_editor_widget, '_cleanup_vlc_player', None)
        shutdown_preview = getattr(
            self.subtitle_editor_widget, "shutdown_media_preview", None
        )
        if callable(shutdown_preview):
            shutdown_preview()
        elif callable(cleanup_player):
            cleanup_player()
            
        # 保存窗口状态
        self.save_settings()
        
        # 清理临时文件
        self.temp_manager.cleanup_all()
        
        event.accept()
    
    def update_action_states(self, index: int):
        """Enable or disable actions based on current page"""
        is_editor = (index == 2)
        # Save actions
        self.save_action.setEnabled(is_editor)
        self.save_as_action.setEnabled(is_editor)
        # Undo/Redo reflect both the current page and actual stack state.
        self._sync_undo_redo_actions()
        # Export action
        self.export_action.setEnabled(is_editor and not self.is_exporting)
    
    @staticmethod
    def _resolve_project_video_path(project_path: str, project_data: Dict[str, Any]):
        """Resolve a v2 project's video, preferring its portable relative path."""
        project_dir = Path(project_path).resolve().parent
        relative = project_data.get("video_path_relative")
        if isinstance(relative, str) and relative.strip():
            candidate = (project_dir / relative).resolve()
            if candidate.is_file():
                return str(candidate)

        stored = project_data.get("video_path")
        if isinstance(stored, str) and stored.strip():
            candidate = Path(stored).expanduser()
            if not candidate.is_absolute():
                candidate = project_dir / candidate
            candidate = candidate.resolve()
            if candidate.is_file():
                return str(candidate)
        return None

    def open_project_file(self, filepath: str = None):
        """打开保存的项目文件(.vtp)并加载到字幕编辑器"""
        if self.has_unsaved_changes and not self.confirm_discard_changes():
            return
        if not filepath:
            filepath, _ = QFileDialog.getOpenFileName(
                self,
                "打开项目文件",
                self.config.get("last_directory", os.path.expanduser("~")),
                "VideoTranslator 项目 (*.vtp)",
            )
        if not filepath:
            return
        filepath = os.path.abspath(os.path.expanduser(filepath))
        # 读取项目数据
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                project_data = json.load(f)
        except Exception as e:
            QMessageBox.warning(self, "打开失败", f"无法读取项目文件: {e}")
            return
        # v2 项目自带视频路径；兼容旧版仅含 segments 的列表格式。
        if isinstance(project_data, list):
            segments_data = project_data
            video_path = self.current_video_path
            source_language = None
            target_language = None
        elif isinstance(project_data, dict) and project_data.get('schema') == 'videotranslator.project':
            if project_data.get('version') != 2:
                QMessageBox.warning(self, "打开失败", "该项目文件版本暂不受支持。")
                return
            segments_data = project_data.get('segments', [])
            video_path = self._resolve_project_video_path(filepath, project_data)
            source_language = project_data.get('source_language')
            target_language = project_data.get('target_language')
        else:
            QMessageBox.warning(self, "打开失败", "不是有效的 VideoTranslator 项目文件。")
            return
        if not isinstance(segments_data, list):
            QMessageBox.warning(self, "打开失败", "项目的字幕数据格式无效。")
            return
        if not video_path or not os.path.exists(video_path):
            selected, _ = QFileDialog.getOpenFileName(
                self, "定位项目视频", os.path.dirname(filepath), "视频文件 (*)"
            )
            video_path = os.path.abspath(selected) if selected else None
        if not video_path or not os.path.exists(video_path):
            QMessageBox.warning(self, "缺少视频", "找不到项目引用的视频，项目未打开。")
            return
        # 切换到编辑器页面
        self.workflow.clear_data()
        self.workflow.set_data('video_path', video_path)
        if source_language:
            self.workflow.set_data('source_language', source_language)
        if target_language:
            self.workflow.set_data('target_language', target_language)
        self.current_video_path = video_path
        self.current_file_path = video_path
        self.current_project_path = filepath
        self.current_subtitle_path = None
        self._set_unsaved_changes(False)
        self.stacked_widget.setCurrentIndex(2)
        # 加载项目数据
        self.subtitle_editor_widget.load_data(video_path,  # 确保这是真正的视频路径 
        {'video_path': video_path, 'segments': segments_data, 'is_project_import': True}  # 添加明确标记
        )
        # Loading can legitimately emit editor change signals while rebuilding
        # list items; an opened project is nevertheless a clean baseline.
        self._set_unsaved_changes(False)
        # 启用保存/导出等操作
        self.save_action.setEnabled(True)
        self.save_as_action.setEnabled(True)
        self._sync_undo_redo_actions()
        self.export_action.setEnabled(True)
        self.status_label.setText(f"已加载项目: {os.path.basename(filepath)}")
        self.config["last_directory"] = os.path.dirname(filepath)
        config_manager = get_config_manager()
        config_manager.add_recent_file(filepath)
        self.config.recent_files = list(config_manager.config.recent_files)
        self.update_recent_menu()

    def show_resume_dialog(self, recovery_info: Dict[str, Any]) -> QMessageBox.StandardButton:
        """显示断点续传确认对话框"""
        
        time_ago = recovery_info['time_ago']
        if time_ago < 3600:
            time_str = f"{int(time_ago // 60)}分钟前"
        elif time_ago < 86400:
            time_str = f"{int(time_ago // 3600)}小时前"
        else:
            time_str = f"{int(time_ago // 86400)}天前"
        
        progress = recovery_info['progress_percent']
        completed_stages = recovery_info['completed_stages']
        next_stage = recovery_info['next_stage']
        
        stage_names = {
            'audio_extraction': '音频提取',
            'speech_recognition': '语音识别',
            'text_translation': '文本翻译',
            'subtitle_generation': '字幕生成'
        }
        
        completed_text = "、".join([stage_names.get(stage, stage) for stage in completed_stages])
        next_text = stage_names.get(next_stage, next_stage) if next_stage else "全部完成"
        
        msg_box = QMessageBox(self)
        msg_box.setIcon(QMessageBox.Icon.Question)
        msg_box.setWindowTitle("发现断点续传数据")
        msg_box.setText("检测到此视频的未完成处理任务")
        msg_box.setInformativeText(
            f"处理进度: {progress:.1f}%\n"
            f"处理时间: {time_str}\n"
            f"已完成: {completed_text}\n"
            f"下一步: {next_text}\n\n"
            f"是否要继续之前的处理？"
        )
        
        # 添加自定义按钮
        continue_btn = msg_box.addButton("继续处理", QMessageBox.ButtonRole.YesRole)
        restart_btn = msg_box.addButton("重新开始", QMessageBox.ButtonRole.NoRole)
        msg_box.addButton("取消", QMessageBox.ButtonRole.RejectRole)
        
        msg_box.setDefaultButton(continue_btn)
        msg_box.exec()
        
        if msg_box.clickedButton() == continue_btn:
            return QMessageBox.StandardButton.Yes
        elif msg_box.clickedButton() == restart_btn:
            return QMessageBox.StandardButton.No
        else:
            return QMessageBox.StandardButton.Cancel
    
    def start_processing_with_resume(self, video_path: str):
        """使用断点续传开始处理"""
        # 从导入页面获取或使用默认参数
        if hasattr(self.video_import_widget, 'get_source_language'):
            source_lang = self.video_import_widget.get_source_language()
            target_lang = self.video_import_widget.get_target_language()
        else:
            # 使用默认值或从检查点恢复
            checkpoint_manager = CheckpointManager()
            checkpoint = checkpoint_manager.load_checkpoint(video_path)
            if checkpoint:
                source_lang = checkpoint.source_language
                target_lang = checkpoint.target_language
            else:
                source_lang = 'auto'
                target_lang = 'zh-CN'
        
        # 保存到工作流数据
        self.workflow.set_data("source_language", source_lang)
        self.workflow.set_data("target_language", target_lang)
        self.workflow.set_data("video_path", video_path)
        
        # 确保当前文件路径设置
        self.current_video_path = video_path
        self.current_file_path = video_path
        
        # 开始处理
        self.processing_widget.start_processing(
            video_path=video_path,
            source_language=source_lang,
            target_language=target_lang,
            whisper_model=self.config.get("whisper_model", "base"),
            translation_provider=self.config.get("translation_provider", "OpenAI")
        )
