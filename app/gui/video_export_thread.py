"""Cancellable background export worker.

All filesystem and FFmpeg work in this module is designed to run on a Qt
worker thread.  A successful export is first written next to its destination
and then committed with :func:`os.replace`, so cancellation and failures never
leave a partially-written destination behind.
"""

from __future__ import annotations

import logging
import os
import signal
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Mapping, Sequence

from PyQt5.QtCore import QObject, pyqtSignal, pyqtSlot

from app.core.subtitle import SubtitleProcessor
from app.core.video import VideoProcessor

logger = logging.getLogger(__name__)


class ExportCancelled(Exception):
    """Internal control-flow exception for a cooperative cancellation."""


class VideoExportWorker(QObject):
    """Export subtitles or a subtitled video without blocking the GUI.

    ``cancel`` is intentionally thread-safe and may be called directly from
    the GUI thread while ``run`` is blocking in a subprocess on the worker
    thread.  Qt queued slots alone cannot provide that guarantee because the
    worker thread's event loop is occupied until ``run`` returns.
    """

    progress = pyqtSignal(int, str)
    succeeded = pyqtSignal(str, str)
    failed = pyqtSignal(str)
    cancelled = pyqtSignal()
    finished = pyqtSignal()

    _SUBTITLE_FORMATS = frozenset({"srt", "vtt", "ass", "ssa", "sbv", "sub"})
    _VIDEO_SUBTITLE_FORMATS = frozenset({"srt", "vtt", "ass", "ssa"})
    _LANGUAGE_MODES = frozenset(
        {"original_only", "translation_only", "bilingual"}
    )
    _VIDEO_FORMATS = frozenset({"mp4", "mkv", "mov", "avi", "webm"})
    _SOFT_SUBTITLE_CODECS = VideoProcessor.SOFT_SUBTITLE_CODECS

    def __init__(self, options: Mapping[str, Any], parent: QObject | None = None):
        super().__init__(parent)
        self.options = dict(options)
        self._cancel_event = threading.Event()
        self._process_lock = threading.Lock()
        self._process: subprocess.Popen[bytes] | None = None

    @property
    def cancellation_requested(self) -> bool:
        return self._cancel_event.is_set()

    def cancel(self) -> None:
        """Request cancellation and wake a running FFmpeg process."""
        self._cancel_event.set()
        with self._process_lock:
            process = self._process
        if process is not None:
            self._signal_process(process, force=False)

    @pyqtSlot()
    def run(self) -> None:
        """Run exactly one export and emit one terminal outcome signal."""
        try:
            output_path, message = self._export()
        except ExportCancelled:
            self.cancelled.emit()
        except Exception as exc:  # surfaced to the GUI as a user-facing failure
            logger.exception("Export failed")
            self.failed.emit(str(exc) or exc.__class__.__name__)
        else:
            self.succeeded.emit(output_path, message)
        finally:
            self.finished.emit()

    def _export(self) -> tuple[str, str]:
        output_dir, filename, subtitle_format, language_mode = self._validate_options()
        segments = self.options.get("subtitle_data")
        if not isinstance(segments, Sequence) or isinstance(segments, (str, bytes)):
            raise ValueError("没有可导出的字幕数据。")

        self._check_cancelled()
        self.progress.emit(5, "正在准备字幕数据…")
        processor = SubtitleProcessor()
        processor.create_from_segments([dict(segment) for segment in segments])
        if not processor.segments:
            raise ValueError("没有有效的字幕片段可导出。")

        is_video_export = bool(
            self.options.get("embed_subtitles")
            or self.options.get("hardcode_subtitles")
        )
        if is_video_export:
            if subtitle_format not in self._VIDEO_SUBTITLE_FORMATS:
                raise ValueError(
                    "SBV/MicroDVD 仅支持字幕文件导出；"
                    "嵌入或烧入视频请选择 SRT、VTT、ASS 或 SSA。"
                )
            return self._export_video(
                processor,
                output_dir,
                filename,
                subtitle_format,
                language_mode,
            )
        return self._export_subtitle(
            processor,
            output_dir,
            filename,
            subtitle_format,
            language_mode,
        )

    def _validate_options(self) -> tuple[Path, str, str, str]:
        output_value = str(self.options.get("output_dir", "")).strip()
        if not output_value:
            raise ValueError("未指定输出目录。")
        output_dir = Path(output_value).expanduser().resolve()
        output_dir.mkdir(parents=True, exist_ok=True)
        if not output_dir.is_dir() or not os.access(output_dir, os.W_OK):
            raise ValueError(f"输出目录不可写：{output_dir}")

        filename = str(self.options.get("filename", "")).strip()
        if not filename or filename in {".", ".."} or Path(filename).name != filename:
            raise ValueError("输出文件名无效。")

        subtitle_format = str(self.options.get("format", "srt")).lower()
        if subtitle_format not in self._SUBTITLE_FORMATS:
            raise ValueError(f"不支持的字幕格式：{subtitle_format}")

        language_mode = str(
            self.options.get("language_option", "translation_only")
        )
        if language_mode not in self._LANGUAGE_MODES:
            raise ValueError(f"不支持的字幕语言模式：{language_mode}")
        return output_dir, filename, subtitle_format, language_mode

    def _export_subtitle(
        self,
        processor: SubtitleProcessor,
        output_dir: Path,
        filename: str,
        subtitle_format: str,
        language_mode: str,
    ) -> tuple[str, str]:
        destination = output_dir / f"{filename}.{subtitle_format}"
        temporary_path = self._reserve_temp_path(output_dir, subtitle_format)
        try:
            self.progress.emit(25, "正在生成字幕文件…")
            processor.save_to_file(
                str(temporary_path),
                subtitle_format,
                language_mode=language_mode,
            )
            self._check_cancelled()
            self._commit(temporary_path, destination)
            self.progress.emit(100, "字幕导出完成")
            return str(destination), "字幕已成功导出"
        finally:
            self._remove_if_exists(temporary_path)

    def _export_video(
        self,
        processor: SubtitleProcessor,
        output_dir: Path,
        filename: str,
        subtitle_format: str,
        language_mode: str,
    ) -> tuple[str, str]:
        video_path = Path(str(self.options.get("video_path", ""))).expanduser().resolve()
        if not video_path.is_file():
            raise FileNotFoundError(f"找不到源视频：{video_path}")

        video_format = str(self.options.get("video_format", "mp4")).lower()
        if video_format == "same":
            video_format = video_path.suffix.lower().lstrip(".") or "mp4"
        if video_format not in self._VIDEO_FORMATS:
            raise ValueError(f"不支持的输出视频格式：{video_format}")

        destination = output_dir / f"{filename}.{video_format}"
        subtitle_temp = self._reserve_temp_path(output_dir, subtitle_format)
        video_temp = self._reserve_temp_path(output_dir, video_format)
        try:
            self.progress.emit(15, "正在生成临时字幕…")
            processor.save_to_file(
                str(subtitle_temp),
                subtitle_format,
                language_mode=language_mode,
            )
            self._check_cancelled()

            hardcode = bool(self.options.get("hardcode_subtitles"))
            if hardcode:
                filter_name = (
                    "ass" if subtitle_format in {"ass", "ssa"} else "subtitles"
                )
                if not VideoProcessor.check_subtitle_filter_available(
                    filter_name=filter_name
                ):
                    raise RuntimeError(
                        f"当前 FFmpeg 缺少 {filter_name} 字幕滤镜（libass）。"
                        "请安装带 libass 的 FFmpeg，或改用软字幕轨道。"
                    )
                self.progress.emit(30, "正在烧入字幕；可随时安全取消…")
                command = self._hardcode_command(
                    video_path, subtitle_temp, video_temp, video_format
                )
                action = "烧入"
            else:
                self.progress.emit(30, "正在嵌入字幕轨道；可随时安全取消…")
                command = self._embed_command(
                    video_path,
                    subtitle_temp,
                    video_temp,
                    video_format,
                    subtitle_format,
                )
                action = "嵌入"

            self._run_ffmpeg(command, cwd=output_dir)
            self._check_cancelled()
            # A zero exit code and a non-empty file are not enough to claim
            # success.  Probe the container and, for soft subtitles, require
            # the subtitle stream before replacing a user's existing output.
            VideoProcessor(temp_dir=output_dir).validate_video_output(
                video_temp,
                require_subtitle=not hardcode,
            )
            self._commit(video_temp, destination)
            self.progress.emit(100, "视频导出完成")
            return str(destination), f"字幕已成功{action}到视频"
        finally:
            self._remove_if_exists(subtitle_temp)
            self._remove_if_exists(video_temp)

    def _embed_command(
        self,
        video_path: Path,
        subtitle_path: Path,
        output_path: Path,
        video_format: str,
        subtitle_format: str,
    ) -> list[str]:
        subtitle_codec = self._SOFT_SUBTITLE_CODECS.get(video_format)
        if subtitle_codec is None:
            raise ValueError(
                f"{video_format.upper()} 容器不支持可靠的软字幕轨道；"
                "请选择 MP4、MKV、MOV 或 WebM，或改用烧入字幕。"
            )
        if video_format == "mkv" and subtitle_format in {"ass", "ssa"}:
            subtitle_codec = "ass"

        language = self._metadata_language(
            str(self.options.get("target_language", "und"))
        )
        command = [
            "ffmpeg",
            "-hide_banner",
            "-nostdin",
            "-y",
            "-i",
            str(video_path),
            "-i",
            str(subtitle_path),
            "-map",
            "0:v:0",
            "-map",
            "0:a?",
            "-map",
            "1:0",
            "-map_metadata",
            "0",
        ]
        if video_format in {"mp4", "mov"}:
            command.extend(
                [
                    "-c:v",
                    "libx264",
                    "-preset",
                    "veryfast",
                    "-crf",
                    "20",
                    "-c:a",
                    "aac",
                ]
            )
        elif video_format == "webm":
            command.extend(
                [
                    "-c:v",
                    "libvpx-vp9",
                    "-crf",
                    "30",
                    "-b:v",
                    "0",
                    "-c:a",
                    "libopus",
                ]
            )
        else:
            command.extend(["-c:v", "copy", "-c:a", "copy"])
        command.extend(
            [
            "-c:s",
            subtitle_codec,
            "-metadata:s:s:0",
            f"language={language}",
            str(output_path),
            ]
        )
        return command

    @staticmethod
    def _hardcode_command(
        video_path: Path,
        subtitle_path: Path,
        output_path: Path,
        video_format: str,
    ) -> list[str]:
        # The subtitle temp name is generated from a restricted ASCII alphabet.
        # Running FFmpeg in that directory avoids fragile filter-path escaping.
        filter_name = "ass" if subtitle_path.suffix.lower() in {".ass", ".ssa"} else "subtitles"
        subtitle_filter = f"{filter_name}=filename={subtitle_path.name}"
        video_codec = "libvpx-vp9" if video_format == "webm" else "libx264"
        command = [
            "ffmpeg",
            "-hide_banner",
            "-nostdin",
            "-y",
            "-i",
            str(video_path),
            "-vf",
            subtitle_filter,
            "-map_metadata",
            "0",
            "-c:v",
            video_codec,
        ]
        if video_codec == "libx264":
            command.extend(["-preset", "medium", "-crf", "20"])
        else:
            command.extend(["-crf", "30", "-b:v", "0"])
        audio_codec = "libopus" if video_format == "webm" else "copy"
        command.extend(["-c:a", audio_codec, str(output_path)])
        return command

    def _run_ffmpeg(self, command: Sequence[str], cwd: Path) -> None:
        """Run a subprocess while remaining responsive to cancellation."""
        self._check_cancelled()
        popen_options: dict[str, Any] = {
            "cwd": str(cwd),
            "stdin": subprocess.DEVNULL,
            "stdout": subprocess.DEVNULL,
        }
        if os.name == "nt":
            popen_options["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            popen_options["start_new_session"] = True

        with tempfile.TemporaryFile() as error_output:
            process = subprocess.Popen(
                list(command), stderr=error_output, **popen_options
            )
            with self._process_lock:
                self._process = process
            try:
                return_code = self._wait_for_process(process)
            finally:
                with self._process_lock:
                    if self._process is process:
                        self._process = None

            error_output.seek(0)
            error_text = error_output.read().decode("utf-8", errors="replace").strip()

        self._check_cancelled()
        if return_code != 0:
            detail = error_text[-4000:] if error_text else "未提供错误详情"
            raise RuntimeError(f"FFmpeg 导出失败（退出码 {return_code}）：\n{detail}")

    def _wait_for_process(self, process: subprocess.Popen[bytes]) -> int:
        while True:
            return_code = process.poll()
            if return_code is not None:
                return return_code
            if self.cancellation_requested:
                self._signal_process(process, force=False)
                deadline = time.monotonic() + 2.0
                while process.poll() is None and time.monotonic() < deadline:
                    time.sleep(0.05)
                if process.poll() is None:
                    self._signal_process(process, force=True)
                    try:
                        process.wait(timeout=2.0)
                    except subprocess.TimeoutExpired:
                        logger.warning("Export subprocess did not exit after being killed")
                raise ExportCancelled
            time.sleep(0.05)

    @staticmethod
    def _signal_process(process: subprocess.Popen[bytes], *, force: bool) -> None:
        if process.poll() is not None:
            return
        try:
            if os.name == "nt":
                process.kill() if force else process.terminate()
            else:
                os.killpg(process.pid, signal.SIGKILL if force else signal.SIGTERM)
        except (ProcessLookupError, PermissionError, OSError):
            logger.debug("Export subprocess had already exited", exc_info=True)

    def _commit(self, temporary_path: Path, destination: Path) -> None:
        self._check_cancelled()
        if destination.exists() and not bool(self.options.get("overwrite_existing")):
            raise FileExistsError(
                f"目标文件在导出期间已出现，未覆盖：{destination}"
            )
        os.replace(temporary_path, destination)

    @staticmethod
    def _reserve_temp_path(directory: Path, extension: str) -> Path:
        descriptor, value = tempfile.mkstemp(
            prefix=".videotranslator-export-",
            suffix=f".{extension}",
            dir=directory,
        )
        os.close(descriptor)
        return Path(value)

    @staticmethod
    def _remove_if_exists(path: Path) -> None:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            logger.warning("Could not remove temporary export file %s", path)

    def _check_cancelled(self) -> None:
        if self.cancellation_requested:
            raise ExportCancelled

    @staticmethod
    def _metadata_language(language: str) -> str:
        primary = language.lower().replace("_", "-").split("-", 1)[0]
        return {
            "zh": "zho",
            "en": "eng",
            "ja": "jpn",
            "ko": "kor",
            "fr": "fra",
            "de": "deu",
            "es": "spa",
            "ru": "rus",
            "it": "ita",
            "pt": "por",
            "ar": "ara",
        }.get(primary, "und")
