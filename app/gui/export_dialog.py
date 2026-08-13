import logging
import os
import re
from datetime import datetime
from typing import Any, Dict, Optional

from PyQt5.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
)

# 创建日志记录器
logger = logging.getLogger(__name__)


class ExportDialog(QDialog):
    """导出选项对话框"""
    
    def __init__(self, parent, config: Dict[str, Any], video_path: str):
        super().__init__(parent)
        self.config = config
        self.video_path = video_path
        self.overwrite_confirmed = False
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
        self.output_path_edit.setAccessibleName("导出目录")
        
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
        self.filename_edit.setAccessibleName("导出文件名")
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
        self.format_combo.addItem("YouTube SBV (.sbv)", "sbv")
        self.format_combo.addItem("MicroDVD (.sub)", "sub")
        self.format_combo.setAccessibleName("字幕导出格式")
        
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
        self.video_format_combo.addItem("MOV", "mov")
        self.video_format_combo.addItem("WebM", "webm")
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
        
        # 保留旧控件属性用于兼容，但统一由下面的语言模式控制。
        self.include_original_checkbox = QCheckBox("在字幕中包含原文")
        self.include_original_checkbox.setVisible(False)
        
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
        self.lang_group.buttonClicked.connect(
            lambda: self.include_original_checkbox.setChecked(
                self.lang_group.checkedId() == 3
            )
        )
        
        lang_layout.addWidget(self.lang_label)
        lang_layout.addWidget(self.lang_original_radio)
        lang_layout.addWidget(self.lang_translation_radio)
        lang_layout.addWidget(self.lang_both_radio)
        lang_layout.addStretch(1)
        content_layout.addLayout(lang_layout)
        
        main_layout.addWidget(content_group)
        
        # 对话框按钮
        self.button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.button_box.button(QDialogButtonBox.StandardButton.Ok).setText("导出")
        self.button_box.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        main_layout.addWidget(self.button_box)
    
    def setup_connections(self):
        """设置信号和槽连接"""
        self.browse_btn.clicked.connect(self.browse_output_dir)
        self.embed_checkbox.toggled.connect(self._update_video_format_enabled)
        self.hardcode_checkbox.toggled.connect(self._update_video_format_enabled)
        
        # 切换字幕格式时禁用不兼容的选项
        self.format_combo.currentIndexChanged.connect(self.update_ui_based_on_format)
        
        # 互斥选项
        self.hardcode_checkbox.toggled.connect(self.handle_hardcode_toggled)
        self.embed_checkbox.toggled.connect(self.handle_embed_toggled)
        
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

    def accept(self):
        """校验目标和覆盖行为后再关闭对话框。"""
        self.overwrite_confirmed = False
        options = self.get_export_options()
        output_dir = options['output_dir']
        if not output_dir:
            QMessageBox.warning(self, "无法导出", "请选择输出目录。")
            return
        try:
            os.makedirs(output_dir, exist_ok=True)
        except OSError as exc:
            QMessageBox.warning(self, "无法导出", f"无法创建输出目录：\n{exc}")
            return
        if not os.path.isdir(output_dir) or not os.access(output_dir, os.W_OK):
            QMessageBox.warning(self, "无法导出", "输出目录不存在或不可写。")
            return
        if not options['filename'] or options['filename'] in {'.', '..'}:
            QMessageBox.warning(self, "无法导出", "请输入有效的文件名。")
            return

        if options['embed_subtitles'] or options['hardcode_subtitles']:
            extension = options.get('video_format', 'mp4')
            if extension == 'same':
                extension = (
                    os.path.splitext(self.video_path)[1].lstrip('.').lower() or 'mp4'
                )
        else:
            extension = options['format']
        destination = os.path.join(output_dir, f"{options['filename']}.{extension}")
        if os.path.exists(destination):
            answer = QMessageBox.question(
                self, "确认覆盖",
                f"目标文件已存在：\n{destination}\n\n是否覆盖？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
            self.overwrite_confirmed = True
        super().accept()
    
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
        """Keep video controls aligned with FFmpeg subtitle input support."""
        current_format = self.format_combo.currentData()

        video_compatible = current_format in {"srt", "vtt", "ass", "ssa"}
        if not video_compatible:
            self.embed_checkbox.setChecked(False)
            self.hardcode_checkbox.setChecked(False)
        self.embed_checkbox.setEnabled(video_compatible)
        self.hardcode_checkbox.setEnabled(video_compatible)
        explanation = (
            ""
            if video_compatible
            else "SBV/MicroDVD 仅用于导出字幕文件；如需视频字幕请选 SRT、VTT 或 ASS。"
        )
        self.embed_checkbox.setToolTip(explanation)
        self.hardcode_checkbox.setToolTip(explanation)
        self._update_video_format_enabled()
    
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

    def _update_video_format_enabled(self):
        self.video_format_combo.setEnabled(
            (self.embed_checkbox.isChecked() or self.hardcode_checkbox.isChecked())
            and self.format_combo.currentData() in {"srt", "vtt", "ass", "ssa"}
        )
    
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
        filename = re.sub(r'[\\/*?:"<>|]', "_", filename).strip().rstrip('.')
        
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
            "include_original": language_option == "bilingual",
            "language_option": language_option,
            # Only an explicit confirmation permits replacing an existing file.
            "overwrite_existing": self.overwrite_confirmed,
        }
        
        # 如果嵌入字幕，添加视频格式
        if self.embed_checkbox.isChecked() or self.hardcode_checkbox.isChecked():
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
            import platform
            import subprocess
            
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
