"""Background worker for the four-stage video translation pipeline."""

from __future__ import annotations

import logging
import os
import tempfile
import threading
import time
import uuid
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from PyQt5.QtCore import QObject, pyqtSignal

from app.core.audio import AudioProcessor
from app.core.speech import SpeechRecognizer
from app.core.subtitle import SubtitleProcessor
from app.core.translation import Translator
from app.utils.checkpoint import CheckpointManager, ProcessingCheckpoint
from app.utils.exception_handler import ErrorCategory, UserFriendlyError

logger = logging.getLogger(__name__)


class ImprovedProcessingWorker(QObject):
    """Run extraction, recognition, translation and subtitle generation.

    The worker itself is moved to one ``QThread`` by :class:`ProcessingWidget`.
    Long-running stages therefore execute directly instead of being wrapped in
    another executor that Python cannot safely terminate.
    """

    finished = pyqtSignal(dict)
    error = pyqtSignal(str)
    cancelled = pyqtSignal()
    progress = pyqtSignal(int, str, int)  # stage number, state, percentage
    log = pyqtSignal(str, int)

    STAGES = (
        "audio_extraction",
        "speech_recognition",
        "text_translation",
        "subtitle_generation",
    )

    def __init__(
        self,
        video_path: str,
        source_language: str,
        target_language: str,
        config: Mapping[str, Any] | Any,
        *,
        audio_processor: AudioProcessor | None = None,
        speech_recognizer: SpeechRecognizer | None = None,
        translator: Translator | None = None,
        subtitle_processor: SubtitleProcessor | None = None,
        checkpoint_manager: CheckpointManager | None = None,
    ) -> None:
        super().__init__()
        self.video_path = str(Path(video_path).expanduser().resolve())
        self.source_language = source_language
        self.target_language = target_language
        self.config = self._snapshot_config(config)

        self.cancel_requested = threading.Event()
        self.audio_processor = audio_processor or AudioProcessor()
        self.speech_recognizer = speech_recognizer
        self.translator = translator
        self.subtitle_processor = subtitle_processor or SubtitleProcessor()
        self.checkpoint_manager = checkpoint_manager or CheckpointManager()

        # These are observability budgets, not unsafe hard timeouts. FFmpeg and
        # Whisper cannot be force-stopped by cancelling a Python Future.
        self.stage_timeouts = {
            "audio_extraction": 300,
            "speech_recognition": 1800,
            "text_translation": 600,
            "subtitle_generation": 60,
        }

    @staticmethod
    def _snapshot_config(config: Mapping[str, Any] | Any) -> dict[str, Any]:
        """Take a task-local copy so settings cannot change halfway through."""

        def value(key: str, default: Any) -> Any:
            getter = getattr(config, "get", None)
            if callable(getter):
                return getter(key, default)
            return getattr(config, key, default)

        raw_keys = value("api_keys", {}) or {}
        api_keys = {
            str(provider).strip().lower(): str(key)
            for provider, key in dict(raw_keys).items()
            if key is not None
        }
        return {
            "whisper_model": str(value("whisper_model", "base")).strip().lower(),
            "translation_provider": str(
                value("translation_provider", "openai")
            ).strip().lower(),
            "api_keys": api_keys,
        }

    @property
    def processing_settings(self) -> dict[str, str]:
        """Settings that define checkpoint compatibility for every stage."""

        return {
            "source_language": self.source_language,
            "target_language": self.target_language,
            "whisper_model": self.config["whisper_model"],
            "translation_provider": self.config["translation_provider"],
        }

    def is_cancelled(self) -> bool:
        return self.cancel_requested.is_set()

    def cancel(self) -> None:
        """Request cooperative cancellation from any thread."""

        self.cancel_requested.set()
        recognizer = self.speech_recognizer
        if recognizer is not None:
            try:
                recognizer.cancel()
            except Exception as exc:  # cancellation must remain best effort
                logger.warning("请求语音识别器停止时出错: %s", exc)

    def cleanup(self) -> None:
        close_translator = getattr(self.translator, "close", None)
        if callable(close_translator):
            try:
                close_translator()
            except Exception as exc:
                logger.warning("关闭翻译缓存时出错: %s", exc)
        try:
            self.audio_processor.cleanup()
        except Exception as exc:
            logger.warning("清理音频资源时出错: %s", exc)

    def run_stage_with_timeout(
        self, stage_name: str, stage_func: Any, *args: Any, **kwargs: Any
    ) -> Any:
        """Run one stage and check cancellation at both safe boundaries."""

        if self.is_cancelled():
            raise InterruptedError("用户取消操作")
        started_at = time.monotonic()
        result = stage_func(*args, **kwargs)
        elapsed = time.monotonic() - started_at
        budget = self.stage_timeouts.get(stage_name)
        if budget and elapsed > budget:
            logger.warning(
                "处理阶段 %s 用时 %.1f 秒，超过建议预算 %s 秒",
                stage_name,
                elapsed,
                budget,
            )
        if self.is_cancelled():
            raise InterruptedError("用户取消操作")
        return result

    def _save_checkpoint(self, stage: str, stage_data: dict[str, Any]) -> None:
        """Save every stage with the exact same compatibility fingerprint."""

        saved = self.checkpoint_manager.save_checkpoint(
            self.video_path,
            stage,
            stage_data,
            **self.processing_settings,
        )
        if not saved:
            self.log.emit("无法保存恢复点；本次处理仍将继续", logging.WARNING)

    @staticmethod
    def _valid_recognition_result(result: Any) -> bool:
        if not isinstance(result, dict):
            return False
        segments = result.get("segments")
        if not isinstance(segments, list) or not segments:
            return False
        for segment in segments:
            if not isinstance(segment, dict) or not isinstance(segment.get("text"), str):
                return False
            try:
                start = float(segment["start"])
                end = float(segment["end"])
            except (KeyError, TypeError, ValueError):
                return False
            if start < 0 or end < start:
                return False
        return True

    @classmethod
    def _valid_translation_result(cls, result: Any, recognition_result: Any) -> bool:
        if not isinstance(result, dict) or not cls._valid_recognition_result(recognition_result):
            return False
        source_segments = recognition_result["segments"]
        original_segments = result.get("original_segments")
        translations = result.get("translated_texts")
        services = result.get("services")
        if not all(isinstance(value, list) for value in (original_segments, translations, services)):
            return False
        expected_length = len(source_segments)
        if not (
            len(original_segments) == len(translations) == len(services) == expected_length
        ):
            return False
        for segment, translated, service in zip(source_segments, translations, services):
            if not isinstance(translated, str) or not isinstance(service, str):
                return False
            if segment.get("text", "").strip() and not translated.strip():
                return False
            if service.lower() in {"fallback", "emergency_fallback"}:
                return False
        return True

    def _checkpoint_stage_is_valid(
        self,
        stage: str,
        data: Any,
        restored: dict[str, dict[str, Any]],
    ) -> bool:
        if not isinstance(data, dict):
            return False
        if stage == "audio_extraction":
            path = data.get("audio_path")
            return isinstance(path, str) and os.path.isfile(path)
        if stage == "speech_recognition":
            return self._valid_recognition_result(data.get("recognition_result"))
        if stage == "text_translation":
            recognition = restored.get("speech_recognition", {}).get(
                "recognition_result"
            )
            return self._valid_translation_result(data.get("translation_result"), recognition)
        if stage == "subtitle_generation":
            path = data.get("subtitle_path")
            return isinstance(path, str) and os.path.isfile(path)
        return False

    def _validated_resume_data(
        self, checkpoint: ProcessingCheckpoint | None
    ) -> dict[str, dict[str, Any]]:
        """Return only a valid, contiguous stage prefix from one loaded snapshot."""

        if checkpoint is None:
            return {}

        completed = set(checkpoint.completed_stages)
        restored: dict[str, dict[str, Any]] = {}
        for stage in self.STAGES:
            if stage not in completed:
                break
            stage_data = checkpoint.stage_data.get(stage)
            if not self._checkpoint_stage_is_valid(stage, stage_data, restored):
                break
            restored[stage] = stage_data

        if set(restored) != completed or len(restored) != len(checkpoint.completed_stages):
            self.log.emit("恢复点不完整，已保留有效阶段并重建后续数据", logging.WARNING)
            self.checkpoint_manager.clear_checkpoint(self.video_path)
            for stage in self.STAGES:
                if stage in restored:
                    self._save_checkpoint(stage, restored[stage])
        return restored

    def extract_audio_stage(self, video_path: str) -> str:
        self.log.emit("开始提取音频...", logging.INFO)
        self.progress.emit(1, "processing", 10)

        audio_path = self.run_stage_with_timeout(
            "audio_extraction",
            self.audio_processor.extract_audio_from_video,
            video_path,
            format="wav",
            sample_rate=16000,
        )
        if not audio_path or not os.path.isfile(audio_path):
            raise UserFriendlyError(
                "音频提取失败",
                ErrorCategory.PROCESSING,
                user_message="无法从视频中提取音频",
                suggestions=["检查视频完整性和格式", "检查磁盘空间与 FFmpeg 安装"],
            )

        path = os.fspath(audio_path)
        self._save_checkpoint("audio_extraction", {"audio_path": path})
        self.progress.emit(1, "complete", 100)
        self.log.emit(f"音频提取完成: {os.path.basename(path)}", logging.INFO)
        return path

    def speech_recognition_stage(self, audio_path: str) -> dict[str, Any]:
        self.log.emit("开始语音识别...", logging.INFO)
        self.progress.emit(2, "processing", 10)

        if self.speech_recognizer is None:
            self.speech_recognizer = SpeechRecognizer(model=self.config["whisper_model"])
        language = (
            None
            if self.source_language.lower() == "auto"
            else self.source_language.split("-")[0]
        )
        result = self.run_stage_with_timeout(
            "speech_recognition",
            self.speech_recognizer.transcribe,
            audio_path,
            language=language,
        )
        if not self._valid_recognition_result(result):
            raise UserFriendlyError(
                "语音识别失败",
                ErrorCategory.PROCESSING,
                user_message="没有识别到带有效时间轴的语音片段",
                suggestions=["检查音频是否包含清晰语音", "确认源语言或更换 Whisper 模型"],
            )

        self._save_checkpoint("speech_recognition", {"recognition_result": result})
        self.progress.emit(2, "complete", 100)
        self.log.emit(f"语音识别完成，共 {len(result['segments'])} 个片段", logging.INFO)
        return result

    def translation_stage(self, recognition_result: dict[str, Any]) -> dict[str, Any]:
        self.log.emit("开始翻译...", logging.INFO)
        self.progress.emit(3, "processing", 10)
        if not self._valid_recognition_result(recognition_result):
            raise UserFriendlyError(
                "没有文本可翻译",
                ErrorCategory.PROCESSING,
                user_message="语音识别结果无效，无法开始翻译",
            )

        if self.translator is None:
            self.translator = Translator(
                primary_service=self.config["translation_provider"],
                api_keys=self.config["api_keys"],
            )

        original_segments = recognition_result["segments"]
        translated_texts: list[str] = []
        services: list[str] = []
        for index, segment in enumerate(original_segments):
            if self.is_cancelled():
                raise InterruptedError("用户取消操作")
            text = segment["text"]
            if text.strip():
                translated = self.translator.translate(
                    text,
                    source_lang=self.source_language,
                    target_lang=self.target_language,
                )
                metadata = getattr(translated, "metadata", None) or {}
                translated_text = getattr(translated, "translated_text", "")
                service = str(getattr(translated, "service", ""))
                if (
                    translated is None
                    or metadata.get("success") is not True
                    or not isinstance(translated_text, str)
                    or not translated_text.strip()
                    or service.lower() in {"fallback", "emergency_fallback"}
                ):
                    provider = self.config["translation_provider"]
                    raise UserFriendlyError(
                        "翻译服务不可用",
                        ErrorCategory.API,
                        user_message=f"{provider} 未返回有效译文，原文不会被伪装成译文。",
                        suggestions=["配置有效的 API 密钥", "检查网络、服务状态和调用配额"],
                    )
                translated_texts.append(translated_text)
                services.append(service)
            else:
                translated_texts.append("")
                services.append("passthrough")
            percent = int((index + 1) / len(original_segments) * 80) + 10
            self.progress.emit(3, "processing", percent)

        result = {
            "original_segments": original_segments,
            "translated_texts": translated_texts,
            "services": services,
        }
        self._save_checkpoint("text_translation", {"translation_result": result})
        self.progress.emit(3, "complete", 100)
        self.log.emit("翻译完成", logging.INFO)
        return result

    def subtitle_generation_stage(self, translation_result: dict[str, Any]) -> str:
        self.log.emit("开始生成字幕...", logging.INFO)
        self.progress.emit(4, "processing", 10)

        recognition = {"segments": translation_result.get("original_segments", [])}
        if not self._valid_translation_result(translation_result, recognition):
            raise UserFriendlyError(
                "字幕数据不完整",
                ErrorCategory.PROCESSING,
                user_message="翻译片段与识别时间轴无法一一对应",
            )

        def generate_subtitles() -> str:
            subtitle_segments = []
            for segment, translated_text in zip(
                translation_result["original_segments"],
                translation_result["translated_texts"],
            ):
                if self.is_cancelled():
                    raise InterruptedError("用户取消操作")
                subtitle_segments.append(
                    {
                        "start": segment["start"],
                        "end": segment["end"],
                        "original_text": segment["text"],
                        "translated_text": translated_text,
                    }
                )

            self.subtitle_processor.create_from_segments(subtitle_segments)
            video_name = Path(self.video_path).stem
            output_path = os.path.join(
                tempfile.gettempdir(),
                f"{video_name}_{uuid.uuid4().hex}_subtitles.srt",
            )
            saved_path = self.subtitle_processor.save_to_file(
                output_path,
                format_type="srt",
                language_mode="translation_only",
            )
            return os.fspath(saved_path)

        result = self.run_stage_with_timeout("subtitle_generation", generate_subtitles)
        if not isinstance(result, str) or not os.path.isfile(result):
            raise UserFriendlyError(
                "字幕生成失败",
                ErrorCategory.PROCESSING,
                user_message="字幕文件未能写入磁盘",
            )

        self._save_checkpoint("subtitle_generation", {"subtitle_path": result})
        self.progress.emit(4, "complete", 100)
        self.log.emit(f"字幕生成完成: {os.path.basename(result)}", logging.INFO)
        return result

    @staticmethod
    def _error_text(error: UserFriendlyError) -> str:
        message = error.user_message
        if error.suggestions:
            message += "\n\n建议：\n" + "\n".join(f"• {item}" for item in error.suggestions)
        return message

    def run(self) -> None:
        """Execute the pipeline and emit exactly one terminal signal."""

        terminal: tuple[str, Any]
        try:
            self.log.emit(f"开始处理视频: {os.path.basename(self.video_path)}", logging.INFO)
            if self.is_cancelled():
                raise InterruptedError("用户取消操作")

            checkpoint = self.checkpoint_manager.load_checkpoint(
                self.video_path,
                **self.processing_settings,
            )
            restored = self._validated_resume_data(checkpoint)
            if restored:
                self.log.emit(
                    f"发现有效恢复点: {list(restored)}",
                    logging.INFO,
                )

            if "audio_extraction" in restored:
                audio_path = restored["audio_extraction"]["audio_path"]
                self.progress.emit(1, "complete", 100)
            else:
                audio_path = self.extract_audio_stage(self.video_path)

            if self.is_cancelled():
                raise InterruptedError("用户取消操作")
            if "speech_recognition" in restored:
                recognition_result = restored["speech_recognition"]["recognition_result"]
                self.progress.emit(2, "complete", 100)
            else:
                recognition_result = self.speech_recognition_stage(audio_path)

            if self.is_cancelled():
                raise InterruptedError("用户取消操作")
            if "text_translation" in restored:
                translation_result = restored["text_translation"]["translation_result"]
                self.progress.emit(3, "complete", 100)
            else:
                translation_result = self.translation_stage(recognition_result)

            if self.is_cancelled():
                raise InterruptedError("用户取消操作")
            if "subtitle_generation" in restored:
                subtitle_path = restored["subtitle_generation"]["subtitle_path"]
                self.progress.emit(4, "complete", 100)
            else:
                subtitle_path = self.subtitle_generation_stage(translation_result)

            segments = [
                {
                    "start": segment["start"],
                    "end": segment["end"],
                    "original_text": segment["text"],
                    "translated_text": translated,
                }
                for segment, translated in zip(
                    recognition_result["segments"],
                    translation_result["translated_texts"],
                )
            ]
            result = {
                "video_path": self.video_path,
                "audio_path": audio_path,
                "recognition_result": recognition_result,
                "translation_result": translation_result,
                "subtitle_path": subtitle_path,
                "segments": segments,
                "status": "completed",
            }
            if not self.checkpoint_manager.clear_checkpoint(self.video_path):
                self.log.emit("处理完成，但旧恢复点未能清除", logging.WARNING)
            self.log.emit("所有处理阶段完成！", logging.INFO)
            terminal = ("finished", result)
        except InterruptedError:
            self.log.emit("处理已被用户取消", logging.WARNING)
            terminal = ("cancelled", None)
        except UserFriendlyError as exc:
            message = self._error_text(exc)
            self.log.emit(f"处理失败: {message}", logging.ERROR)
            terminal = ("error", message)
        except Exception as exc:
            logger.exception("处理过程中发生未知错误")
            message = f"处理失败: {exc}"
            self.log.emit(message, logging.ERROR)
            terminal = ("error", message)
        finally:
            # Never tell the GUI that the thread is terminal before owned
            # resources have actually been released.
            self.cleanup()

        kind, payload = terminal
        if kind == "finished":
            self.finished.emit(payload)
        elif kind == "cancelled":
            self.cancelled.emit()
        else:
            self.error.emit(payload)
