import os
import logging
import re
from datetime import datetime
from typing import Dict, Any, List, Optional

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox,
    QFileDialog, QCheckBox, QLineEdit, QFormLayout, QGroupBox,
    QDialogButtonBox, QProgressBar, QRadioButton, QButtonGroup, QSpacerItem,
    QSizePolicy, QMessageBox
)
from PyQt5.QtCore import Qt, pyqtSignal, QSize, QTimer
from PyQt5.QtGui import QIcon

from app.core.subtitle import SubtitleProcessor
from app.resources.icons import IconManager

# 创建日志记录器
logger = logging.getLogger(__name__)


class ExportDialog(QDialog):
    """导出选项对话框"""
    
    # 信号：导出进度更新
    progress_updated = pyqtSignal(int, str)
    
    def __init__(self, parent, config: Dict[str, Any], video_path: str):
        super().__init__(parent)
        self.config = config
        self.video_path = video_path
        # 使用父窗口的 IconManager 实例
        self.icon_manager = parent.icon_manager
        
        # 设置窗口属性
        self.setWindowTitle("导出选项")
        self.setMinimumWidth(500)
        self.setModal(True)
        
        self.setup_ui()
        self.setup_connections()
        self.initialize_values()
    
    def setup_ui(self):
        """设置用户界面"""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(10)
        
        # 创建表单布局
        form_layout = QFormLayout()
        form_layout.setSpacing(10)
        form_layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        
        # 输出路径
        self.output_path_label = QLabel("输出目录:")
        self.output_path_edit = QLineEdit()
        self.output_path_edit.setReadOnly(True)
        
        path_layout = QHBoxLayout()
        path_layout.addWidget(self.output_path_edit)
        
        self.browse_btn = QPushButton("浏览...")
        self.browse_btn.setIcon(self.icon_manager.get_icon("folder"))
        path_layout.addWidget(self.browse_btn)
        
        form_layout.addRow(self.output_path_label, path_layout)
        
        # 文件名模板
        self.filename_label = QLabel("文件名模板:")
        self.filename_edit = QLineEdit()
        self.filename_edit.setPlaceholderText("例如: {original_name}_translated")
        form_layout.addRow(self.filename_label, self.filename_edit)
        
        # 添加模板帮助标签
        help_text = "可用变量: {original_name}, {source_lang}, {target_lang}, {date}"
        help_label = QLabel(help_text)
        help_label.setStyleSheet("color: gray; font-size: 9pt;")
        form_layout.addRow("", help_label)
        
        # 将表单布局添加到主布局
        main_layout.addLayout(form_layout)
        
        # 导出格式选择（分组框）
        format_group = QGroupBox("导出格式")
        format_layout = QVBoxLayout(format_group)
        
        # 字幕格式选择
        subtitle_layout = QHBoxLayout()
        self.format_label = QLabel("字幕格式:")
        self.format_combo = QComboBox()
        self.format_combo.addItem("SRT 格式 (.srt)", "srt")
        self.format_combo.addItem("WebVTT 格式 (.vtt)", "vtt")
        self.format_combo.addItem("Advanced SubStation Alpha (.ass)", "ass")
        self.format_combo.addItem("SubStation Alpha (.ssa)", "ssa")
        
        subtitle_layout.addWidget(self.format_label)
        subtitle_layout.addWidget(self.format_combo)
        subtitle_layout.addStretch(1)
        format_layout.addLayout(subtitle_layout)
        
        # 视频选项
        self.embed_checkbox = QCheckBox("将字幕嵌入视频")
        format_layout.addWidget(self.embed_checkbox)
        
        # 视频格式选项（嵌入字幕时可选）
        video_options_layout = QHBoxLayout()
        self.video_format_label = QLabel("视频格式:")
        self.video_format_combo = QComboBox()
        self.video_format_combo.addItem("MP4", "mp4")
        self.video_format_combo.addItem("MKV", "mkv")
        self.video_format_combo.addItem("与源格式相同", "same")
        self.video_format_combo.setEnabled(False)  # 初始禁用
        
        video_options_layout.addWidget(self.video_format_label)
        video_options_layout.addWidget(self.video_format_combo)
        video_options_layout.addStretch(1)
        format_layout.addLayout(video_options_layout)
        
        # 硬字幕选项（烧入字幕）
        self.hardcode_checkbox = QCheckBox("烧入字幕（硬字幕）")
        format_layout.addWidget(self.hardcode_checkbox)
        
        main_layout.addWidget(format_group)
        
        # 字幕内容选项（分组框）
        content_group = QGroupBox("字幕内容选项")
        content_layout = QVBoxLayout(content_group)
        
        # 包含原文
        self.include_original_checkbox = QCheckBox("在字幕中包含原文")
        content_layout.addWidget(self.include_original_checkbox)
        
        # 语言选项
        lang_layout = QHBoxLayout()
        self.lang_label = QLabel("显示语言:")
        
        self.lang_original_radio = QRadioButton("仅原文")
        self.lang_translation_radio = QRadioButton("仅译文")
        self.lang_both_radio = QRadioButton("双语")
        self.lang_both_radio.setChecked(True)
        
        self.lang_group = QButtonGroup(self)
        self.lang_group.addButton(self.lang_original_radio, 1)
        self.lang_group.addButton(self.lang_translation_radio, 2)
        self.lang_group.addButton(self.lang_both_radio, 3)
        
        lang_layout.addWidget(self.lang_label)
        lang_layout.addWidget(self.lang_original_radio)
        lang_layout.addWidget(self.lang_translation_radio)
        lang_layout.addWidget(self.lang_both_radio)
        lang_layout.addStretch(1)
        content_layout.addLayout(lang_layout)
        
        main_layout.addWidget(content_group)
        
        # 进度条（初始隐藏）
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setVisible(False)
        main_layout.addWidget(self.progress_bar)
        
        # 状态标签（初始隐藏）
        self.status_label = QLabel("")
        self.status_label.setVisible(False)
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(self.status_label)
        
        # 对话框按钮
        self.button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.button_box.button(QDialogButtonBox.StandardButton.Ok).setText("导出")
        self.button_box.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        main_layout.addWidget(self.button_box)
    
    def setup_connections(self):
        """设置信号和槽连接"""
        self.browse_btn.clicked.connect(self.browse_output_dir)
        self.embed_checkbox.toggled.connect(self.video_format_combo.setEnabled)
        
        # 切换字幕格式时禁用不兼容的选项
        self.format_combo.currentIndexChanged.connect(self.update_ui_based_on_format)
        
        # 互斥选项
        self.hardcode_checkbox.toggled.connect(self.handle_hardcode_toggled)
        self.embed_checkbox.toggled.connect(self.handle_embed_toggled)
        
        # 导出进度信号
        self.progress_updated.connect(self.update_progress)
        
        # 对话框按钮
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
    
    def initialize_values(self):
        """初始化表单值"""
        # 设置默认输出目录
        default_output_dir = self.config.get("output_dir", os.path.expanduser("~/Videos"))
        
        # 【修复】确保转换为字符串类型（处理Path对象、字符串或其他类型）
        try:
            if hasattr(default_output_dir, '__fspath__'):  # Path对象
                default_output_dir_str = str(default_output_dir)
            else:
                default_output_dir_str = str(default_output_dir)
        except Exception as e:
            logger.warning(f"转换输出目录路径时出错: {e}，使用默认路径")
            default_output_dir_str = os.path.expanduser("~/Videos")
        
        self.output_path_edit.setText(default_output_dir_str)
        
        # 设置默认文件名模板
        original_name = os.path.splitext(os.path.basename(self.video_path))[0]
        self.filename_edit.setText(f"{original_name}_translated")
        
        # 设置默认格式
        default_format = self.config.get("default_subtitle_format", "srt")
        for i in range(self.format_combo.count()):
            if self.format_combo.itemData(i) == default_format:
                self.format_combo.setCurrentIndex(i)
                break
        
        # 默认双语字幕
        self.include_original_checkbox.setChecked(True)
    
    def browse_output_dir(self):
        """浏览并选择输出目录"""
        current_dir = self.output_path_edit.text()
        if not os.path.isdir(current_dir):
            current_dir = os.path.expanduser("~")
            
        dir_path = QFileDialog.getExistingDirectory(
            self, 
            "选择输出目录", 
            current_dir,
            QFileDialog.Option.ShowDirsOnly
        )
        
        if dir_path:
            self.output_path_edit.setText(dir_path)
    
    def update_ui_based_on_format(self):
        """基于所选格式更新UI选项"""
        current_format = self.format_combo.currentData()
        
        # 某些格式可能不支持特定功能
        if current_format in ["srt", "vtt"]:
            self.embed_checkbox.setEnabled(True)
        else:
            # ASS/SSA格式可能有特殊考虑
            pass
    
    def handle_hardcode_toggled(self, checked: bool):
        """处理烧入字幕选项切换"""
        if checked:
            # 如果选择烧入字幕，则禁用嵌入字幕（互斥）
            self.embed_checkbox.setChecked(False)
    
    def handle_embed_toggled(self, checked: bool):
        """处理嵌入字幕选项切换"""
        if checked:
            # 如果选择嵌入字幕，则禁用烧入字幕（互斥）
            self.hardcode_checkbox.setChecked(False)
    
    def update_progress(self, percent: int, message: str):
        """更新进度条和状态消息"""
        if not self.progress_bar.isVisible():
            self.progress_bar.setVisible(True)
            self.status_label.setVisible(True)
            # 禁用表单元素
            self.setFormEnabled(False)
            
        self.progress_bar.setValue(percent)
        self.status_label.setText(message)
        
        # 如果完成，重新启用表单
        if percent >= 100:
            self.setFormEnabled(True)
            # 延迟一段时间后隐藏进度条
            QTimer.singleShot(3000, lambda: self.progress_bar.setVisible(False))
    
    def setFormEnabled(self, enabled: bool):
        """启用或禁用表单元素"""
        self.browse_btn.setEnabled(enabled)
        self.filename_edit.setEnabled(enabled)
        self.format_combo.setEnabled(enabled)
        self.embed_checkbox.setEnabled(enabled)
        self.video_format_combo.setEnabled(enabled and self.embed_checkbox.isChecked())
        self.hardcode_checkbox.setEnabled(enabled)
        self.include_original_checkbox.setEnabled(enabled)
        self.lang_original_radio.setEnabled(enabled)
        self.lang_translation_radio.setEnabled(enabled)
        self.lang_both_radio.setEnabled(enabled)
        self.button_box.button(QDialogButtonBox.StandardButton.Ok).setEnabled(enabled)
    
    def get_export_options(self) -> Dict[str, Any]:
        """
        获取导出选项
        
        Returns:
            包含所有导出选项的字典
        """
        # 准备文件名
        filename_template = self.filename_edit.text()
        base_filename = os.path.basename(self.video_path)
        original_name = os.path.splitext(base_filename)[0]
        
        # 替换模板变量
        filename = filename_template.replace("{original_name}", original_name)
        filename = filename.replace("{date}", datetime.now().strftime("%Y%m%d"))
        
        # 源语言和目标语言需要从外部传入，这里先占位
        source_lang = self.config.get("source_language", "unknown")
        target_lang = self.config.get("target_language", "unknown")
        filename = filename.replace("{source_lang}", source_lang)
        filename = filename.replace("{target_lang}", target_lang)
        
        # 清理文件名，移除非法字符
        filename = re.sub(r'[\\/*?:"<>|]', "_", filename)
        
        # 获取输出目录
        output_dir = self.output_path_edit.text()
        
        # 获取字幕格式
        subtitle_format = self.format_combo.currentData()
        
        # 确定语言选项
        language_mode = self.lang_group.checkedId()
        if language_mode == 1:
            language_option = "original_only"
        elif language_mode == 2:
            language_option = "translation_only"
        else:
            language_option = "bilingual"
        
        # 构建选项字典
        options = {
            "output_dir": output_dir,
            "filename": filename,
            "format": subtitle_format,
            "embed_subtitles": self.embed_checkbox.isChecked(),
            "hardcode_subtitles": self.hardcode_checkbox.isChecked(),
            "include_original": self.include_original_checkbox.isChecked(),
            "language_option": language_option
        }
        
        # 如果嵌入字幕，添加视频格式
        if self.embed_checkbox.isChecked():
            options["video_format"] = self.video_format_combo.currentData()
        
        return options
    
    def show_export_result(self, success: bool, message: str, output_path: Optional[str] = None):
        """
        显示导出结果消息框
        
        Args:
            success: 导出是否成功
            message: 消息文本
            output_path: 输出文件路径（如果成功）
        """
        if success:
            result = QMessageBox.information(
                self,
                "导出成功",
                f"{message}\n\n文件已保存到:\n{output_path}",
                QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Open,
                QMessageBox.StandardButton.Ok
            )
            
            # 如果用户选择"打开"，则打开输出文件或目录
            if result == QMessageBox.StandardButton.Open and output_path:
                self.open_output_file(output_path)
        else:
            QMessageBox.warning(
                self,
                "导出失败",
                f"{message}",
                QMessageBox.StandardButton.Ok
            )
    
    def open_output_file(self, path: str):
        """
        打开输出文件或目录
        
        Args:
            path: 文件或目录路径
        """
        try:
            import subprocess
            import platform
            
            if platform.system() == "Windows":
                os.startfile(path)
            elif platform.system() == "Darwin":  # macOS
                subprocess.Popen(["open", path])
            else:  # Linux
                subprocess.Popen(["xdg-open", path])
        except Exception as e:
            logging.error(f"无法打开文件: {str(e)}")
            QMessageBox.warning(
                self,
                "无法打开文件",
                f"无法打开文件或目录:\n{str(e)}",
                QMessageBox.StandardButton.Ok
            )
