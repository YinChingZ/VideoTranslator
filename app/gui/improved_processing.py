#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Improved processing worker with better thread management and timeout handling.
改进的处理器，具有更好的线程管理和超时处理机制。
"""

import os
import time
import logging
import threading
from typing import Optional, Dict, Any
from PyQt5.QtCore import QObject, pyqtSignal, QTimer, QThread
from concurrent.futures import ThreadPoolExecutor, TimeoutError, as_completed

from app.core.video import VideoProcessor
from app.core.audio import AudioProcessor
from app.core.speech import SpeechRecognizer
from app.core.translation import Translator
from app.core.subtitle import SubtitleProcessor
from app.utils.logger import setup_logger

logger = setup_logger()
from app.utils.checkpoint import CheckpointManager
from app.utils.exception_handler import UserFriendlyError, ErrorCategory
from app.utils.recovery_manager import retry

logger = logging.getLogger(__name__)


class ImprovedProcessingWorker(QObject):
    """改进的处理工作器，具有更好的线程管理和超时控制"""
    
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
        
        # 取消标志
        self.cancel_requested = threading.Event()
        
        # 处理器实例
        self.video_processor = VideoProcessor()
        self.audio_processor = AudioProcessor()
        self.speech_recognizer = None  # 延迟初始化
        self.translator = None  # 延迟初始化
        self.subtitle_processor = SubtitleProcessor()
        
        # 断点续传管理器
        self.checkpoint_manager = CheckpointManager()
        
        # 线程池
        self.executor = ThreadPoolExecutor(max_workers=2)
        
        # 阶段超时设置（秒）
        self.stage_timeouts = {
            'audio_extraction': 300,  # 5分钟
            'speech_recognition': 1800,  # 30分钟
            'text_translation': 600,  # 10分钟
            'subtitle_generation': 60  # 1分钟
        }
    
    def is_cancelled(self) -> bool:
        """检查是否已请求取消"""
        return self.cancel_requested.is_set()
    
    def cancel(self):
        """请求取消处理"""
        self.cancel_requested.set()
        if self.executor:
            self.executor.shutdown(wait=False)
        
        # 如果语音识别器正在运行，也取消它
        if self.speech_recognizer:
            self.speech_recognizer.cancel_flag = True
    
    def cleanup(self):
        """清理资源"""
        try:
            if self.executor:
                self.executor.shutdown(wait=True)
            if self.audio_processor:
                self.audio_processor.cleanup()
        except Exception as e:
            logger.warning(f"清理资源时出错: {e}")
    
    def run_stage_with_timeout(self, stage_name: str, stage_func, *args, **kwargs):
        """在指定超时时间内运行阶段任务"""
        timeout = self.stage_timeouts.get(stage_name, 600)
        
        def target():
            return stage_func(*args, **kwargs)
        
        future = self.executor.submit(target)
        
        try:
            # 等待结果，带超时
            result = future.result(timeout=timeout)
            return result
        except TimeoutError:
            future.cancel()
            raise UserFriendlyError(
                f"{stage_name} 超时",
                ErrorCategory.PROCESSING,
                user_message=f"处理阶段 '{stage_name}' 超时，请尝试重新处理",
                suggestions=[
                    "检查系统性能",
                    "尝试使用更快的处理设置",
                    "分段处理较长的视频",
                    "重启应用程序"
                ]
            )
        except Exception as e:
            future.cancel()
            raise e
    
    def extract_audio_stage(self, video_path: str) -> str:
        """音频提取阶段"""
        if self.is_cancelled():
            raise InterruptedError("用户取消操作")
        
        self.log.emit('开始提取音频...', logging.INFO)
        self.progress.emit(1, 'processing', 10)
        
        def extract_audio():
            if self.is_cancelled():
                raise InterruptedError("用户取消操作")
            return self.audio_processor.extract_audio_from_video(
                video_path, format='wav', sample_rate=16000
            )
        
        audio_path = self.run_stage_with_timeout('audio_extraction', extract_audio)
        
        if not audio_path or not os.path.exists(audio_path):
            raise UserFriendlyError(
                "音频提取失败",
                ErrorCategory.PROCESSING,
                user_message="无法从视频中提取音频",
                suggestions=[
                    "检查视频文件完整性",
                    "确认视频格式受支持",
                    "检查磁盘空间",
                    "尝试其他视频文件"
                ]
            )
        
        # 保存检查点
        self.checkpoint_manager.save_checkpoint(
            video_path, 'audio_extraction',
            {'audio_path': str(audio_path)},
            source_language=self.source_language,
            target_language=self.target_language,
            whisper_model=self.config.get('whisper_model', 'base'),
            translation_provider=self.config.get('translation_provider', 'openai')
        )
        
        self.progress.emit(1, 'complete', 100)
        self.log.emit(f'音频提取完成: {os.path.basename(audio_path)}', logging.INFO)
        return str(audio_path)
    
    def speech_recognition_stage(self, audio_path: str) -> dict:
        """语音识别阶段"""
        if self.is_cancelled():
            raise InterruptedError("用户取消操作")
        
        self.log.emit('开始语音识别...', logging.INFO)
        self.progress.emit(2, 'processing', 10)
        
        # 延迟初始化语音识别器
        if not self.speech_recognizer:
            model_name = self.config.get('whisper_model', 'base')
            self.speech_recognizer = SpeechRecognizer(model=model_name)
        
        def transcribe():
            if self.is_cancelled():
                raise InterruptedError("用户取消操作")
            
            lang = None if self.source_language == 'auto' else self.source_language.split('-')[0]
            return self.speech_recognizer.transcribe(audio_path, language=lang)
        
        result = self.run_stage_with_timeout('speech_recognition', transcribe)
        
        if not result:
            raise UserFriendlyError(
                "语音识别失败",
                ErrorCategory.PROCESSING,
                user_message="无法识别音频中的语音内容",
                suggestions=[
                    "检查音频质量",
                    "尝试选择正确的源语言",
                    "使用更大的Whisper模型",
                    "确认音频包含语音内容"
                ]
            )
        
        # 保存检查点
        self.checkpoint_manager.save_checkpoint(
            self.video_path, 'speech_recognition',
            {'recognition_result': result}
        )
        
        self.progress.emit(2, 'complete', 100)
        self.log.emit(f'语音识别完成，识别到 {len(result.get("segments", []))} 个片段', logging.INFO)
        return result
    
    def translation_stage(self, recognition_result: dict) -> dict:
        """翻译阶段"""
        if self.is_cancelled():
            raise InterruptedError("用户取消操作")
        
        self.log.emit('开始翻译...', logging.INFO)
        self.progress.emit(3, 'processing', 10)
        
        # 延迟初始化翻译器
        if not self.translator:
            api_keys = self.config.get("api_keys", {})
            translation_provider = self.config.get('translation_provider', 'openai')
            self.translator = Translator(
                primary_service=translation_provider.lower(),
                api_keys=api_keys
            )
        
        def translate():
            if self.is_cancelled():
                raise InterruptedError("用户取消操作")
            
            # 提取文本进行翻译
            texts = [segment.get('text', '') for segment in recognition_result.get('segments', [])]
            if not texts:
                raise UserFriendlyError(
                    "没有文本可翻译",
                    ErrorCategory.PROCESSING,
                    user_message="语音识别结果中没有找到文本内容"
                )
            
            # 批量翻译
            translated_texts = []
            for i, text in enumerate(texts):
                if self.is_cancelled():
                    raise InterruptedError("用户取消操作")
                
                if text.strip():
                    translated = self.translator.translate(
                        text, 
                        source_lang=self.source_language,
                        target_lang=self.target_language
                    )
                    translated_texts.append(translated.translated_text if translated else text)
                else:
                    translated_texts.append(text)
                
                # 更新进度
                progress = int((i + 1) / len(texts) * 80) + 10
                self.progress.emit(3, 'processing', progress)
            
            # 构建翻译结果
            translation_result = {
                'original_segments': recognition_result.get('segments', []),
                'translated_texts': translated_texts
            }
            
            return translation_result
        
        result = self.run_stage_with_timeout('text_translation', translate)
        
        # 保存检查点
        self.checkpoint_manager.save_checkpoint(
            self.video_path, 'text_translation',
            {'translation_result': result}
        )
        
        self.progress.emit(3, 'complete', 100)
        self.log.emit('翻译完成', logging.INFO)
        return result
    
    def subtitle_generation_stage(self, translation_result: dict) -> str:
        """字幕生成阶段"""
        import tempfile
        import os
        
        if self.is_cancelled():
            raise InterruptedError("用户取消操作")
        
        self.log.emit('开始生成字幕...', logging.INFO)
        self.progress.emit(4, 'processing', 10)
        
        def generate_subtitles():
            if self.is_cancelled():
                raise InterruptedError("用户取消操作")
            
            # 生成字幕文件
            original_segments = translation_result.get('original_segments', [])
            translated_texts = translation_result.get('translated_texts', [])
            
            # 创建字幕段
            subtitle_segments = []
            for i, (segment, translated_text) in enumerate(zip(original_segments, translated_texts)):
                subtitle_segments.append({
                    'start': segment.get('start', 0),
                    'end': segment.get('end', 0),
                    'text': translated_text
                })
            
            # 先创建字幕段，然后保存到文件
            self.subtitle_processor.create_from_segments(subtitle_segments)
            
            # 生成输出文件路径
            import tempfile
            import os
            video_name = os.path.splitext(os.path.basename(self.video_path))[0]
            subtitle_path = os.path.join(tempfile.gettempdir(), f"{video_name}_subtitles.srt")
            
            # 保存字幕文件
            saved_path = self.subtitle_processor.save_to_file(subtitle_path, format_type='srt')
            return saved_path
        
        result = self.run_stage_with_timeout('subtitle_generation', generate_subtitles)
        
        # 确保result是字符串路径
        if isinstance(result, list):
            # 如果result是列表，可能是create_from_segments的返回值被意外返回
            # 重新生成字幕文件
            import tempfile
            import os
            video_name = os.path.splitext(os.path.basename(self.video_path))[0]
            subtitle_path = os.path.join(tempfile.gettempdir(), f"{video_name}_subtitles.srt")
            result = self.subtitle_processor.save_to_file(subtitle_path, format_type='srt')
            logger.warning(f"字幕生成阶段返回了列表，已重新生成字幕文件: {result}")
        
        # 保存检查点
        self.checkpoint_manager.save_checkpoint(
            self.video_path, 'subtitle_generation',
            {'subtitle_path': str(result)}
        )
        
        self.progress.emit(4, 'complete', 100)
        self.log.emit(f'字幕生成完成: {os.path.basename(result)}', logging.INFO)
        return str(result)
    
    def run(self):
        """主处理函数"""
        try:
            self.log.emit(f'开始处理视频: {os.path.basename(self.video_path)}', logging.INFO)
            
            # 检查断点续传
            checkpoint = self.checkpoint_manager.load_checkpoint(self.video_path)
            completed_stages = checkpoint.completed_stages if checkpoint else []
            
            if completed_stages:
                self.log.emit(f'发现断点续传数据，已完成阶段: {completed_stages}', logging.INFO)
            
            # 初始化结果变量
            audio_path = None
            recognition_result = None
            translation_result = None
            subtitle_path = None
            
            # 阶段1：音频提取
            if 'audio_extraction' not in completed_stages:
                audio_path = self.extract_audio_stage(self.video_path)
            else:
                # 从检查点恢复
                stage_data = self.checkpoint_manager.get_stage_data(self.video_path, 'audio_extraction')
                audio_path = stage_data.get('audio_path') if stage_data else None
                self.progress.emit(1, 'complete', 100)
                self.log.emit(f'从检查点恢复音频文件: {os.path.basename(audio_path)}', logging.INFO)
            
            if self.is_cancelled():
                return
            
            # 阶段2：语音识别
            if 'speech_recognition' not in completed_stages:
                recognition_result = self.speech_recognition_stage(audio_path)
            else:
                # 从检查点恢复
                stage_data = self.checkpoint_manager.get_stage_data(self.video_path, 'speech_recognition')
                recognition_result = stage_data.get('recognition_result') if stage_data else None
                self.progress.emit(2, 'complete', 100)
                self.log.emit('从检查点恢复语音识别结果', logging.INFO)
            
            if self.is_cancelled():
                return
            
            # 阶段3：翻译
            if 'text_translation' not in completed_stages:
                translation_result = self.translation_stage(recognition_result)
            else:
                # 从检查点恢复
                stage_data = self.checkpoint_manager.get_stage_data(self.video_path, 'text_translation')
                translation_result = stage_data.get('translation_result') if stage_data else None
                self.progress.emit(3, 'complete', 100)
                self.log.emit('从检查点恢复翻译结果', logging.INFO)
            
            if self.is_cancelled():
                return
            
            # 阶段4：字幕生成
            if 'subtitle_generation' not in completed_stages:
                subtitle_path = self.subtitle_generation_stage(translation_result)
            else:
                # 从检查点恢复
                stage_data = self.checkpoint_manager.get_stage_data(self.video_path, 'subtitle_generation')
                subtitle_path = stage_data.get('subtitle_path') if stage_data else None
                self.progress.emit(4, 'complete', 100)
                self.log.emit(f'从检查点恢复字幕文件: {os.path.basename(subtitle_path)}', logging.INFO)
            
            # 构建最终结果
            # 确保包含segments数据供字幕编辑器使用
            segments_data = []
            if recognition_result and 'segments' in recognition_result:
                original_segments = recognition_result['segments']
                translated_texts = translation_result.get('translated_texts', []) if translation_result else []
                
                # 组合原始段和翻译文本
                for i, segment in enumerate(original_segments):
                    translated_text = translated_texts[i] if i < len(translated_texts) else ''
                    segments_data.append({
                        'start': segment.get('start', 0),
                        'end': segment.get('end', 0),
                        'original_text': segment.get('text', ''),
                        'translated_text': translated_text
                    })
            
            final_result = {
                'video_path': self.video_path,
                'audio_path': audio_path,
                'recognition_result': recognition_result,
                'translation_result': translation_result,
                'subtitle_path': subtitle_path,
                'segments': segments_data,  # 添加segments数据
                'status': 'completed'
            }
            
            self.log.emit('所有处理阶段完成！', logging.INFO)
            self.finished.emit(final_result)
            
        except InterruptedError:
            self.log.emit('处理已被用户取消', logging.WARNING)
            self.error.emit('处理已取消')
        except UserFriendlyError as e:
            self.log.emit(f'处理失败: {e.message}', logging.ERROR)
            self.error.emit(str(e))
        except Exception as e:
            logger.exception("处理过程中发生未知错误")
            self.log.emit(f'处理失败: {str(e)}', logging.ERROR)
            self.error.emit(f'处理失败: {str(e)}')
        finally:
            self.cleanup()
