import os
import sys
import logging
from typing import Dict, Any, Optional

from PyQt5.QtWidgets import (
    QMainWindow, QStackedWidget, QToolBar, QStatusBar, QMenuBar, 
    QMenu, QMessageBox, QFileDialog, QLabel, QApplication, QAction
)

from PyQt5.QtCore import Qt, QSettings, pyqtSignal, QSize
from PyQt5.QtGui import QIcon, QKeySequence, QCloseEvent

from app.gui.video_import import VideoImportWidget
from app.gui.processing import ProcessingWidget
from app.gui.subtitle_editor import SubtitleEditorWidget
from app.gui.export_dialog import ExportDialog
from app.utils.temp_files import TempFileManager
from app.resources.icons import IconManager
from app.resources.styles import StyleManager
from app.core.subtitle import SubtitleProcessor
from app.config import get_config_manager, ConfigManager, AppConfig
from PyQt5.QtWidgets import QDialog, QDialogButtonBox, QFormLayout, QLineEdit, QComboBox, QVBoxLayout
from app.config import WHISPER_MODELS, TRANSLATION_PROVIDERS
from app.utils.checkpoint import CheckpointManager
from app.utils.exception_handler import ExceptionHandler, handle_exception, exception_handler

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
        self.config_manager = config_manager
        self.config = config
        # Layout
        layout = QVBoxLayout(self)
        form = QFormLayout()
        # Whisper model
        self.model_combo = QComboBox()
        for model in WHISPER_MODELS:
            self.model_combo.addItem(model)
        self.model_combo.setCurrentText(self.config.get('whisper_model', 'base'))
        form.addRow("Whisper模型:", self.model_combo)
        # Translation provider
        self.provider_combo = QComboBox()
        for prov in TRANSLATION_PROVIDERS:
            self.provider_combo.addItem(prov)
        self.provider_combo.setCurrentText(self.config.get('translation_provider', 'OpenAI'))
        form.addRow("翻译提供商:", self.provider_combo)
        # API key
        self.api_edit = QLineEdit()
        current_key = self.config_manager.get_api_key(self.provider_combo.currentText())
        self.api_edit.setText(current_key)
        form.addRow("API Key:", self.api_edit)
        # Update API key when provider changes
        self.provider_combo.currentTextChanged.connect(
            lambda prov: self.api_edit.setText(self.config_manager.get_api_key(prov))
        )
        layout.addLayout(form)
        # Buttons
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def accept(self):
        # Save whisper model and translation provider
        self.config['whisper_model'] = self.model_combo.currentText()
        prov = self.provider_combo.currentText()
        self.config['translation_provider'] = prov
        # Update API key in config and persist
        key = self.api_edit.text().strip()
        # Ensure api_keys dict exists
        self.config.setdefault('api_keys', {})[prov] = key
        # Persist entire config including updated api_keys
        self.config_manager.save_config(self.config)
        super().accept()

class MainWindow(QMainWindow):
    """应用主窗口"""
    
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
        self.current_file_path = None
        
        self.setup_ui()
        self.setup_menu()
        self.setup_toolbar()
        self.setup_statusbar()
        self.setup_connections()
        self.apply_styles()
        
        # 设置窗口属性
        self.setWindowTitle("视频翻译处理系统")
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
    
    def setup_connections(self):
        """设置信号和槽连接"""
        # 导入页面信号
        self.video_import_widget.continue_signal.connect(self.start_processing)
        
        # 处理页面信号
        self.processing_widget.processing_completed.connect(self.processing_complete)
        self.processing_widget.processing_error.connect(self.processing_error)
        
        # 编辑页面信号，使用 segmentsChanged 信号标记未保存更改
        self.subtitle_editor_widget.segmentsChanged.connect(self.mark_unsaved_changes)
        
        # 进度更新信号
        self.progress_update.connect(self.update_progress)
        
        # When page changes, update action states
        self.stacked_widget.currentChanged.connect(self.update_action_states)
    
    def apply_styles(self):
        """应用应用程序样式"""
        if self.config.get("dark_mode", False):
            self.style_manager.apply_dark_theme(self)
        else:
            self.style_manager.apply_light_theme(self)
    
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
                action.triggered.connect(self.open_recent_file)
                self.recent_menu.addAction(action)
    
    def open_video_dialog(self):
        """打开视频文件对话框"""
        if self.has_unsaved_changes and not self.confirm_discard_changes():
            return
        
        file_filter = "视频文件 ({});;所有文件 (*)".format(
            " ".join(f"*.{ext}" for ext in self.config.get("supported_video_formats", ["mp4", "mkv"])))
        
        filepath, _ = QFileDialog.getOpenFileName(
            self, "打开视频文件", 
            self.config.get("last_directory", os.path.expanduser("~")),
            file_filter
        )
        
        if filepath:
            self.open_video(filepath)
    
    @exception_handler("打开视频文件")
    def open_video(self, filepath: str):
        """打开视频文件
        
        Args:
            filepath: 视频文件路径
        """
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
        from app.config import ConfigManager
        config_manager = ConfigManager()
        config_manager.add_recent_file(filepath)
        self.update_recent_menu()
        
        # 如果有未保存的更改，提示保存
        if self.has_unsaved_changes:
            result = self.confirm_discard_changes()
            if not result:
                return
        
        # 清除旧数据
        self.workflow.clear_data()
        
        # 设置新文件路径
        self.current_file_path = filepath
        self.setWindowTitle(f"视频翻译处理系统 - {os.path.basename(filepath)}")
        
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
        
        # 预加载视频基本信息
        try:
            import ffmpeg
            probe = ffmpeg.probe(filepath)
            video_info = next((stream for stream in probe['streams'] if stream['codec_type'] == 'video'), None)
            
            if video_info:
                self.workflow.set_data("video_info", {
                    "width": int(video_info.get('width', 0)),
                    "height": int(video_info.get('height', 0)),
                    "duration": float(probe.get('format', {}).get('duration', 0)),
                    "format": probe.get('format', {}).get('format_name', '未知')
                })
                logging.info(f"已加载视频信息: {self.workflow.get_data('video_info')}")
        except Exception as e:
            logging.warning(f"预加载视频信息失败: {str(e)}")
            # 不阻止文件打开，只是记录警告
        
        # 设置视频路径到导入页面
        self.video_import_widget.set_video_path(filepath)
        self.workflow.go_to_import()
        
        # 重置未保存状态
        self.has_unsaved_changes = False
        self.status_label.setText(f"已加载: {os.path.basename(filepath)}")
    
    def open_recent_file(self):
        """打开最近的文件"""
        action = self.sender()
        if action:
            filepath = action.data()
            if os.path.exists(filepath):
                self.open_video(filepath)
            else:
                QMessageBox.warning(self, "文件不存在", f"文件 {filepath} 不存在或已被移动。")
                
                # 从最近文件列表中移除
                from app.config import ConfigManager
                config_manager = ConfigManager()
                config = config_manager.load_config()
                if filepath in config["recent_files"]:
                    config["recent_files"].remove(filepath)
                    config_manager.save_config(config)
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
            if self.current_file_path and self.current_file_path.lower().endswith('.vtp'):
                save_path = self.current_file_path
            else:
                save_path = os.path.splitext(video_path)[0] + ".vtp"
        # Write project file
        try:
            import json, dataclasses
            with open(save_path, 'w', encoding='utf-8') as f:
                json.dump([dataclasses.asdict(seg) for seg in subtitle_data], f, ensure_ascii=False, indent=2)
            self.current_file_path = save_path
            self.has_unsaved_changes = False
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
        if self.current_file_path and self.current_file_path.lower().endswith('.vtp'):
            default_path = self.current_file_path
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
        # Determine video path from workflow or processing results
        video_path = self.workflow.get_data('video_path')
        results = self.workflow.get_data('processing_results')
        if not video_path and isinstance(results, dict):
            video_path = results.get('video_path')
        if not video_path:
            QMessageBox.warning(self, "导出失败", "未找到视频文件路径，无法导出。")
            return
        self.current_file_path = video_path
        if (self.stacked_widget.currentIndex() != 2):  # 不在编辑页面
            QMessageBox.information(self, "无法导出", "请先完成字幕编辑后再导出。")
            return
            
        dialog = ExportDialog(self, self.config, video_path)
        if dialog.exec():
            subtitle_data = self.subtitle_editor_widget.get_processed_segments()
            export_options = dialog.get_export_options()
            
            # 开始导出进程
            self.status_label.setText("正在导出...")
            export_options["subtitle_data"] = subtitle_data
            export_options["video_path"] = self.current_file_path
            
            import dataclasses
            try:
                # 将 SubtitleSegment 对象转换为字典并通过 SubtitleProcessor 导出
                segments_dicts = [dataclasses.asdict(seg) for seg in subtitle_data]
                processor = SubtitleProcessor()
                processor.create_from_segments(segments_dicts)
                
                # 根据导出选项决定处理方式
                if export_options.get("embed_subtitles", False) or export_options.get("hardcode_subtitles", False):
                    # 导出视频（嵌入或烧入字幕）
                    self._export_video_with_subtitles(processor, export_options, dialog)
                else:
                    # 仅导出字幕文件
                    self._export_subtitle_file(processor, export_options, dialog)
                    
            except Exception as e:
                logging.error(f"导出失败: {e}")
                self.status_label.setText("导出失败")
                dialog.show_export_result(False, f"导出时发生错误:\n{str(e)}")
    
    def _export_subtitle_file(self, processor, export_options, dialog):
        """导出字幕文件"""
        output_path = os.path.join(
            export_options["output_dir"], 
            export_options["filename"] + "." + export_options["format"]
        )
        
        # 生成字幕文件
        processor.save_to_file(
            output_path, 
            export_options["format"], 
            export_options.get("include_original", False)
        )
        
        # 更新状态并通知用户
        self.status_label.setText(f"导出完成: {os.path.basename(output_path)}")
        dialog.show_export_result(True, "字幕已成功导出", output_path)
    
    def _export_video_with_subtitles(self, processor, export_options, dialog):
        """导出带字幕的视频"""
        from app.core.video import VideoProcessor
        import tempfile
        
        video_processor = VideoProcessor()
        
        # 创建临时字幕文件
        with tempfile.NamedTemporaryFile(suffix=f".{export_options['format']}", delete=False) as tmp_file:
            temp_subtitle_path = tmp_file.name
        
        try:
            # 先生成字幕文件
            processor.save_to_file(
                temp_subtitle_path, 
                export_options["format"], 
                export_options.get("include_original", False)
            )
            
            # 确定输出视频格式
            video_format = export_options.get("video_format", "mp4")
            if video_format == "same":
                # 保持与源视频相同的格式
                original_ext = os.path.splitext(export_options["video_path"])[1]
                video_format = original_ext[1:] if original_ext else "mp4"
            
            # 构建输出视频路径
            output_video_path = os.path.join(
                export_options["output_dir"],
                export_options["filename"] + f".{video_format}"
            )
            
            # 根据选项决定是嵌入还是烧入字幕
            if export_options.get("hardcode_subtitles", False):
                # 烧入字幕（硬字幕）
                self.status_label.setText("正在烧入字幕到视频...")
                success = video_processor.burn_subtitles_to_video(
                    export_options["video_path"],
                    temp_subtitle_path,
                    output_video_path
                )
                action_desc = "烧入"
            else:
                # 嵌入字幕（软字幕）
                self.status_label.setText("正在嵌入字幕到视频...")
                success = video_processor.embed_subtitles_to_video(
                    export_options["video_path"],
                    temp_subtitle_path,
                    output_video_path
                )
                action_desc = "嵌入"
            
            if success:
                self.status_label.setText(f"导出完成: {os.path.basename(output_video_path)}")
                dialog.show_export_result(True, f"字幕已成功{action_desc}到视频", output_video_path)
            else:
                self.status_label.setText("导出失败")
                dialog.show_export_result(False, f"字幕{action_desc}到视频失败")
                
        finally:
            # 清理临时字幕文件
            try:
                os.unlink(temp_subtitle_path)
            except Exception as e:
                logging.warning(f"清理临时字幕文件失败: {e}")
    
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
        # 将结果保存到工作流
        self.workflow.set_data("processing_results", result_data)
        
        # 转到编辑器页面
        self.workflow.go_to_editor()
        
        # 加载数据到编辑器
        self.subtitle_editor_widget.load_data(
            self.current_file_path,
            result_data
        )
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
        
        # Enable save and undo/redo actions
        self.save_action.setEnabled(True)
        self.save_as_action.setEnabled(True)
        self.undo_action.setEnabled(True)
        self.redo_action.setEnabled(True)
    
    def processing_error(self, error_message):
        """处理错误回调"""
        QMessageBox.critical(self, "处理错误", f"处理视频时发生错误:\n{error_message}")
        self.workflow.go_to_import()
        self.status_label.setText("处理失败")
    
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
    
    def mark_unsaved_changes(self):
        """标记有未保存的更改"""
        if not self.has_unsaved_changes:
            self.has_unsaved_changes = True
            self.setWindowTitle(f"{self.windowTitle()} *")
    
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
        config_manager = ConfigManager()
        dialog = SettingsDialog(config_manager, self.config, self)
        dialog.exec()
    
    def show_about(self):
        """显示关于对话框"""
        QMessageBox.about(
            self,
            "关于视频翻译处理系统",
            f"视频翻译处理系统 v{self.config.get('app_version', '1.0.0')}\n\n"
            "一个用于视频翻译和字幕生成的工具。\n\n"
            "© 2023 VideoTranslator团队"
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
    
    def closeEvent(self, event: QCloseEvent):
        """窗口关闭事件处理"""
        if self.has_unsaved_changes and not self.confirm_discard_changes():
            event.ignore()
            return
            
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
        # Undo/Redo
        self.undo_action.setEnabled(is_editor)
        self.redo_action.setEnabled(is_editor)
        # Export action
        self.export_action.setEnabled(is_editor)
    
    def open_project_file(self):
        """打开保存的项目文件(.vtp)并加载到字幕编辑器"""
        # 选择项目文件
        filepath, _ = QFileDialog.getOpenFileName(
            self, "打开项目文件", self.config.get("last_directory", os.path.expanduser("~")),
            "VideoTranslator 项目 (*.vtp)"
        )
        if not filepath:
            return
        # 读取项目数据
        try:
            import json
            with open(filepath, 'r', encoding='utf-8') as f:
                segments_data = json.load(f)
        except Exception as e:
            QMessageBox.warning(self, "打开失败", f"无法读取项目文件: {e}")
            return
        # 检查是否已加载视频
        video_path = self.current_file_path
        if not video_path or not os.path.exists(video_path):
            QMessageBox.warning(self, "缺少视频", "请先打开视频文件，然后再加载项目文件。")
            return
        # 切换到编辑器页面
        self.workflow.set_data('video_path', video_path)
        self.setWindowTitle(f"视频翻译处理系统 - {os.path.basename(video_path)} [项目: {os.path.basename(filepath)}]")
        self.stacked_widget.setCurrentIndex(2)
        # 加载项目数据
        self.subtitle_editor_widget.load_data(video_path,  # 确保这是真正的视频路径 
        {'video_path': video_path, 'segments': segments_data, 'is_project_import': True}  # 添加明确标记
        )
        # 启用保存/导出等操作
        self.save_action.setEnabled(True)
        self.save_as_action.setEnabled(True)
        self.undo_action.setEnabled(True)
        self.redo_action.setEnabled(True)
        self.export_action.setEnabled(True)
        self.status_label.setText(f"已加载项目: {os.path.basename(filepath)}")
        self.has_unsaved_changes = False

    def show_resume_dialog(self, recovery_info: Dict[str, Any]) -> QMessageBox.StandardButton:
        """显示断点续传确认对话框"""
        import datetime
        
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
        cancel_btn = msg_box.addButton("取消", QMessageBox.ButtonRole.RejectRole)
        
        msg_box.setDefaultButton(continue_btn)
        result = msg_box.exec()
        
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
        self.current_file_path = video_path
        
        # 开始处理
        self.processing_widget.start_processing(
            video_path=video_path,
            source_language=source_lang,
            target_language=target_lang,
            whisper_model=self.config.get("whisper_model", "base"),
            translation_provider=self.config.get("translation_provider", "OpenAI")
        )
