import os
import logging
import threading
import time
from typing import Dict, Any, List, Optional, Callable

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QProgressBar, 
    QTextEdit, QScrollArea, QFrame, QSpacerItem, QSizePolicy
)
from PyQt5.QtCore import Qt, pyqtSignal, QTimer, pyqtSlot, QObject, QThread
from PyQt5.QtGui import QTextCursor, QIcon, QColor

from app.core.video import VideoProcessor
from app.core.audio import AudioProcessor
from app.core.speech import SpeechRecognizer
from app.core.translation import Translator
from app.core.subtitle import SubtitleProcessor
from app.utils.logger import add_log_viewer
from app.utils.checkpoint import CheckpointManager
from app.utils.exception_handler import ExceptionHandler, handle_exception, exception_handler, UserFriendlyError, ErrorCategory
from app.utils.recovery_manager import retry, with_recovery, RetryConfig, RetryStrategy
from app.gui.improved_processing import ImprovedProcessingWorker

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

class ProcessingWorker(QObject):
    """后台处理任务，发射信号到主线程更新UI"""
    finished = pyqtSignal(dict)
    error = pyqtSignal(str)
    progress = pyqtSignal(int, str, int)  # stage, status, progress
    log = pyqtSignal(str, int)

    def __init__(self, video_path, source_language, target_language, config):
        super().__init__()
        self.video_path = video_path
        self.source_language = source_language
        self.target_language = target_language
        self.config = config
        self.video_processor = VideoProcessor()
        self.audio_processor = AudioProcessor()
        
        # 延迟初始化以避免重复加载大模型
        self.speech_recognizer = None
        self.translator = None
        self.subtitle_processor = SubtitleProcessor()
        
        # 断点续传管理器
        self.checkpoint_manager = CheckpointManager()
        
        # 阶段映射
        self.stage_map = {
            'audio_extraction': 1,
            'speech_recognition': 2, 
            'text_translation': 3,
            'subtitle_generation': 4
        }

    @with_recovery({'operation': 'video_processing'})
    @pyqtSlot()
    def run(self):
        try:
            # 检查是否可以断点续传
            checkpoint = self.checkpoint_manager.load_checkpoint(self.video_path)
            completed_stages = checkpoint.completed_stages if checkpoint else []
            
            self.log.emit(f'开始处理视频: {os.path.basename(self.video_path)}', logging.INFO)
            if completed_stages:
                self.log.emit(f'发现断点续传数据，已完成阶段: {completed_stages}', logging.INFO)
            
            audio_path = None
            recog = None
            trans = None
            
            # Stage 1: 音频提取（带重试机制）
            if 'audio_extraction' not in completed_stages:
                self.progress.emit(1, 'processing', 0)
                self.log.emit('开始提取音频...', logging.INFO)
                
                @retry(max_attempts=3, delay=2.0, exceptions=(Exception,))
                def extract_audio_with_retry():
                    return self.audio_processor.extract_audio_from_video(
                        self.video_path, format='wav', sample_rate=16000)
                
                try:
                    audio_path = extract_audio_with_retry()
                    if not audio_path:
                        raise UserFriendlyError(
                            "音频提取失败", 
                            ErrorCategory.PROCESSING,
                            user_message="无法从视频中提取音频，请检查视频文件是否完整",
                            suggestions=[
                                "确认视频文件完整且未损坏",
                                "尝试使用其他视频格式",
                                "检查FFmpeg是否正确安装",
                                "确保有足够的磁盘空间"
                            ]
                        )
                    
                    # 保存检查点
                    self.checkpoint_manager.save_checkpoint(
                        self.video_path, 'audio_extraction', 
                        {'audio_path': audio_path},
                        source_language=self.source_language,
                        target_language=self.target_language,
                        whisper_model=self.config.get('whisper_model', 'base'),
                        translation_provider=self.config.get('translation_provider', 'openai')
                    )
                    
                    self.progress.emit(1, 'complete', 100)
                    self.log.emit(f'音频提取完成: {audio_path}', logging.INFO)
                except Exception as e:
                    self.log.emit(f'音频提取失败: {str(e)}', logging.ERROR)
                    if not isinstance(e, UserFriendlyError):
                        # 将通用异常转换为用户友好的异常
                        raise UserFriendlyError(
                            f"音频提取失败: {str(e)}", 
                            ErrorCategory.PROCESSING,
                            user_message="音频提取过程中遇到问题",
                            suggestions=[
                                "检查视频文件是否损坏",
                                "确认视频格式受支持",
                                "重试操作",
                                "联系技术支持"
                            ]
                        )
                    raise
            else:
                # 从检查点恢复
                stage_data = self.checkpoint_manager.get_stage_data(self.video_path, 'audio_extraction')
                audio_path = stage_data.get('audio_path') if stage_data else None
                if not audio_path or not os.path.exists(audio_path):
                    raise UserFriendlyError(
                        "检查点中的音频文件不存在", 
                        ErrorCategory.FILE_SYSTEM,
                        user_message="断点续传数据损坏，音频文件丢失",
                        suggestions=[
                            "重新开始处理",
                            "检查磁盘空间",
                            "确认文件未被删除"
                        ]
                    )
                self.progress.emit(1, 'complete', 100)
                self.log.emit(f'从检查点恢复音频文件: {audio_path}', logging.INFO)

            # Stage 2: 语音识别（带重试机制）
            if 'speech_recognition' not in completed_stages:
                self.progress.emit(2, 'processing', 0)
                self.log.emit('开始语音识别...', logging.INFO)
                
                @retry(max_attempts=2, delay=5.0, exceptions=(Exception,))
                def transcribe_with_retry():
                    # 延迟初始化语音识别器
                    if self.speech_recognizer is None:
                        model_name = self.config.get('whisper_model', 'base')
                        self.speech_recognizer = SpeechRecognizer(model=model_name)
                    
                    lang = None if self.source_language=='auto' else self.source_language.split('-')[0]
                    return self.speech_recognizer.transcribe(audio_path, language=lang)
                
                try:
                    recog = transcribe_with_retry()
                    if not recog:
                        raise UserFriendlyError(
                            "语音识别失败", 
                            ErrorCategory.PROCESSING,
                            user_message="无法识别音频中的语音内容",
                            suggestions=[
                                "确认音频质量清晰",
                                "尝试选择正确的源语言",
                                "检查Whisper模型是否可用",
                                "尝试使用其他Whisper模型"
                            ]
                        )
                    
                    # 保存检查点
                    self.checkpoint_manager.save_checkpoint(
                        self.video_path, 'speech_recognition', 
                        {'recognition_result': recog}
                    )
                    
                    self.progress.emit(2, 'complete', 100)
                    self.log.emit('语音识别完成', logging.INFO)
                except Exception as e:
                    self.log.emit(f'语音识别失败: {str(e)}', logging.ERROR)
                    if not isinstance(e, UserFriendlyError):
                        # 检查具体错误类型
                        error_msg = str(e).lower()
                        if 'memory' in error_msg or 'out of memory' in error_msg:
                            raise UserFriendlyError(
                                f"语音识别内存不足: {str(e)}", 
                                ErrorCategory.MEMORY,
                                user_message="系统内存不足，无法完成语音识别",
                                suggestions=[
                                    "关闭其他应用程序释放内存",
                                    "使用较小的Whisper模型",
                                    "将视频分段处理",
                                    "增加系统内存"
                                ]
                            )
                        elif 'model' in error_msg or 'load' in error_msg:
                            raise UserFriendlyError(
                                f"语音识别模型错误: {str(e)}", 
                                ErrorCategory.DEPENDENCY,
                                user_message="Whisper模型加载失败",
                                suggestions=[
                                    "检查网络连接",
                                    "重新下载Whisper模型",
                                    "尝试使用其他模型",
                                    "检查磁盘空间"
                                ]
                            )
                        else:
                            raise UserFriendlyError(
                                f"语音识别失败: {str(e)}", 
                                ErrorCategory.PROCESSING,
                                user_message="语音识别过程中遇到问题",
                                suggestions=[
                                    "重试操作",
                                    "检查音频文件完整性",
                                    "尝试其他设置",
                                    "联系技术支持"
                                ]
                            )
                    raise
            else:
                # 从检查点恢复
                stage_data = self.checkpoint_manager.get_stage_data(self.video_path, 'speech_recognition')
                recog = stage_data.get('recognition_result') if stage_data else None
                if not recog:
                    raise UserFriendlyError(
                        "检查点中的语音识别结果不存在", 
                        ErrorCategory.FILE_SYSTEM,
                        user_message="断点续传数据损坏，语音识别结果丢失",
                        suggestions=[
                            "重新开始语音识别",
                            "检查存储空间",
                            "确认数据未被清理"
                        ]
                    )
                self.progress.emit(2, 'complete', 100)
                self.log.emit('从检查点恢复语音识别结果', logging.INFO)

            # Stage 3: 文本翻译（带重试机制）
            if 'text_translation' not in completed_stages:
                self.progress.emit(3, 'processing', 0)
                self.log.emit('开始翻译字幕...', logging.INFO)
                
                @retry(max_attempts=3, delay=3.0, backoff=1.5, 
                      exceptions=(ConnectionError, TimeoutError, Exception))
                def translate_with_retry():
                    # 延迟初始化翻译器
                    if self.translator is None:
                        api_keys = self.config.get("api_keys", {})
                        translation_provider = self.config.get('translation_provider', 'openai')
                        self.translator = Translator(
                            primary_service=translation_provider.lower(),
                            api_keys=api_keys
                        )
                    
                    texts = [seg['text'] for seg in recog['segments']]
                    return self.translator.batch_translate(
                        texts, 
                        source_lang=recog.get('detected_language', self.source_language), 
                        target_lang=self.target_language
                    )
                
                try:
                    trans = translate_with_retry()
                    if not trans:
                        raise UserFriendlyError(
                            "字幕翻译失败", 
                            ErrorCategory.API,
                            user_message="翻译服务无法处理字幕内容",
                            suggestions=[
                                "检查网络连接",
                                "验证API密钥是否有效",
                                "尝试使用其他翻译服务",
                                "检查API配额是否充足"
                            ]
                        )
                    
                    # 保存检查点
                    self.checkpoint_manager.save_checkpoint(
                        self.video_path, 'text_translation', 
                        {'translation_result': [t.translated_text for t in trans]}
                    )
                    
                    self.progress.emit(3, 'complete', 100)
                    self.log.emit('字幕翻译完成', logging.INFO)
                except Exception as e:
                    self.log.emit(f'字幕翻译失败: {str(e)}', logging.ERROR)
                    if not isinstance(e, UserFriendlyError):
                        error_msg = str(e).lower()
                        if any(keyword in error_msg for keyword in ['api', 'unauthorized', '401', '403']):
                            if 'key' in error_msg or 'token' in error_msg or 'unauthorized' in error_msg:
                                raise UserFriendlyError(
                                    f"API密钥无效: {str(e)}", 
                                    ErrorCategory.API,
                                    user_message="翻译服务API密钥无效或已过期",
                                    suggestions=[
                                        "检查API密钥是否正确",
                                        "确认API密钥未过期",
                                        "重新配置API密钥",
                                        "联系API服务提供商"
                                    ]
                                )
                            elif 'quota' in error_msg or 'limit' in error_msg:
                                raise UserFriendlyError(
                                    f"API配额不足: {str(e)}", 
                                    ErrorCategory.API,
                                    user_message="翻译服务配额已用尽",
                                    suggestions=[
                                        "等待配额重置",
                                        "升级API服务计划",
                                        "使用其他翻译服务",
                                        "分批处理内容"
                                    ]
                                )
                            elif 'rate' in error_msg or 'too many' in error_msg:
                                raise UserFriendlyError(
                                    f"API调用过于频繁: {str(e)}", 
                                    ErrorCategory.API,
                                    user_message="API调用频率过高",
                                    suggestions=[
                                        "稍等几分钟后重试",
                                        "减少并发请求",
                                        "升级API服务计划"
                                    ]
                                )
                        elif 'network' in error_msg or 'connection' in error_msg or 'timeout' in error_msg:
                            raise UserFriendlyError(
                                f"网络连接失败: {str(e)}", 
                                ErrorCategory.NETWORK,
                                user_message="无法连接到翻译服务",
                                suggestions=[
                                    "检查网络连接",
                                    "尝试使用VPN",
                                    "稍后重试",
                                    "检查防火墙设置"
                                ]
                            )
                        else:
                            raise UserFriendlyError(
                                f"翻译失败: {str(e)}", 
                                ErrorCategory.PROCESSING,
                                user_message="翻译过程中遇到问题",
                                suggestions=[
                                    "重试操作",
                                    "检查源语言设置",
                                    "尝试其他翻译服务",
                                    "联系技术支持"
                                ]
                            )
                    raise
            else:
                # 从检查点恢复
                stage_data = self.checkpoint_manager.get_stage_data(self.video_path, 'text_translation')
                translations = stage_data.get('translation_result') if stage_data else None
                if not translations:
                    raise UserFriendlyError(
                        "检查点中的翻译结果不存在", 
                        ErrorCategory.FILE_SYSTEM,
                        user_message="断点续传数据损坏，翻译结果丢失",
                        suggestions=[
                            "重新开始翻译",
                            "检查存储空间",
                            "确认数据未被清理"
                        ]
                    )
                # 重建翻译结果对象
                from app.core.translation import TranslationResult
                trans = [TranslationResult(
                    translated_text=t, 
                    original_text="", 
                    source_lang=self.source_language, 
                    target_lang=self.target_language
                ) for t in translations]
                self.progress.emit(3, 'complete', 100)
                self.log.emit('从检查点恢复翻译结果', logging.INFO)

            # Stage 4: 字幕生成
            if 'subtitle_generation' not in completed_stages:
                self.progress.emit(4, 'processing', 0)
                self.log.emit('正在生成字幕文件...', logging.INFO)
                try:
                    # 合并识别和翻译结果
                    for i, seg in enumerate(recog['segments']):
                        seg['original'] = seg.get('text','')
                        seg['translation'] = trans[i].translated_text if i < len(trans) else ''
                    
                    self.subtitle_processor.create_from_segments(recog['segments'])
                    subtitle_path = self.subtitle_processor.save_to_file(
                        os.path.splitext(self.video_path)[0]+'.srt', 
                        format_type='srt', 
                        include_original=True
                    )
                    if not subtitle_path:
                        raise Exception('字幕生成失败')
                    
                    # 保存检查点
                    self.checkpoint_manager.save_checkpoint(
                        self.video_path, 'subtitle_generation', 
                        {'subtitle_path': subtitle_path, 'segments': recog['segments']}
                    )
                    
                    self.progress.emit(4, 'complete', 100)
                    self.log.emit(f'字幕文件生成完成: {subtitle_path}', logging.INFO)
                except Exception as e:
                    self.log.emit(f'字幕生成失败: {str(e)}', logging.ERROR)
                    raise
            else:
                # 从检查点恢复
                stage_data = self.checkpoint_manager.get_stage_data(self.video_path, 'subtitle_generation')
                subtitle_path = stage_data.get('subtitle_path') if stage_data else None
                if stage_data and 'segments' in stage_data:
                    recog['segments'] = stage_data['segments']
                if not subtitle_path:
                    raise Exception('检查点中的字幕文件不存在，需要重新生成')
                self.progress.emit(4, 'complete', 100)
                self.log.emit(f'从检查点恢复字幕文件: {subtitle_path}', logging.INFO)

            # 处理完成，清除检查点
            self.checkpoint_manager.clear_checkpoint(self.video_path)
            
            # 返回最终结果
            result = {
                'video_path': self.video_path,
                'audio_path': audio_path,
                'source_language': recog.get('detected_language', self.source_language),
                'target_language': self.target_language,
                'segments': recog['segments'],
                'subtitle_path': subtitle_path
            }
            self.finished.emit(result)
            
        except Exception as e:
            error_msg = f"处理失败: {str(e)}"
            self.log.emit(error_msg, logging.ERROR)
            self.error.emit(error_msg)

class ProcessingWidget(QWidget):
    """处理状态显示界面"""
    
    # 信号：当处理完成时发出
    processing_completed = pyqtSignal(dict)
    
    # 信号：当处理出错时发出
    processing_error = pyqtSignal(str)
    
    # 信号：日志消息，用于线程安全更新日志区域
    log_signal = pyqtSignal(str, str)  
    
    def __init__(self, config: Dict[str, Any], parent=None):
        super().__init__(parent)
        self.config = config
        self.processing_thread = None
        self.is_processing = False
        self.start_time = 0
        self.result_data = {}
        
        # 处理器实例
        self.video_processor = VideoProcessor()
        self.audio_processor = AudioProcessor()
        self.speech_recognizer = None  # 延迟初始化
        self.translator = None  # 延迟初始化
        self.subtitle_processor = SubtitleProcessor()
        
        self.setup_ui()
        self.setup_connections()
        
        # 使用日志查看器并连接日志信号
        add_log_viewer(self.append_log)
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
    
    def start_processing(self, video_path: str, source_language: str, target_language: str,
                      whisper_model: str = "base", translation_provider: str = "OpenAI"):
        """
        开始处理视频
        
        Args:
            video_path: 视频文件路径
            source_language: 源语言代码
            target_language: 目标语言代码
            whisper_model: Whisper模型类型
            translation_provider: 翻译服务提供商
        """
        if self.is_processing:
            logging.warning("已有处理任务在进行中")
            return
        
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
        self.thread = QThread(self)
        self.worker = ImprovedProcessingWorker(video_path, source_language, target_language, self.config)
        self.worker.moveToThread(self.thread)
        
        # 连接信号
        self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(self.on_processing_finished)
        self.worker.error.connect(self.on_processing_error)
        self.worker.progress.connect(self.handle_stage_progress)
        self.worker.log.connect(self.append_log)
        
        # 清理连接
        self.worker.finished.connect(self.thread.quit)
        self.worker.error.connect(self.thread.quit)
        self.thread.finished.connect(self.worker.cleanup)
        
        # 启动线程
        self.thread.start()
    
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
        self.processing_completed.emit(result)
        self.is_processing = False

    def on_processing_error(self, msg):
        self.processing_error.emit(msg)
        self.is_processing = False

    def cancel_processing(self):
        """取消处理过程"""
        if not self.is_processing:
            return
        
        self.append_log("用户取消处理")
        
        # 取消改进的处理器
        if hasattr(self.worker, 'cancel'):
            self.worker.cancel()
        
        # 强制停止线程
        if hasattr(self, 'thread') and self.thread.isRunning():
            self.thread.requestInterruption()
            self.thread.quit()
            self.thread.wait(3000)  # 等待3秒
            if self.thread.isRunning():
                self.thread.terminate()  # 强制终止
        
        # 标记为非处理状态
        self.is_processing = False
        # 停止定时器在主线程执行
        QTimer.singleShot(0, self.timer.stop)
        
        # 发出错误信号通知取消
        self.processing_error.emit("用户取消处理")
    
    def reset_ui(self):
        """重置界面状态"""
        self.log_text.clear()
        self.status_label.setText("准备处理...")
        self.time_label.setText("预计剩余时间: 计算中...")
    
    def update_elapsed_time(self):
        """更新已用时间和预计剩余时间"""
        if not self.is_processing:
            return
        
        elapsed = time.time() - self.start_time
        elapsed_formatted = self._format_time(elapsed)
        
        # 简单估计总时间和剩余时间
        # 这里使用一个非常简单的估计方法，根据各阶段的完成情况
        completed_stages = 0
        total_progress = 0
        
        for stage in [self.extraction_stage, self.recognition_stage, 
                    self.translation_stage, self.subtitle_stage]:
            if stage.status == "complete":
                completed_stages += 1
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
        self.log_signal.emit(message, color)
    
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
