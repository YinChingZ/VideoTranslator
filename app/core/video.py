"""Safe, path-independent FFmpeg video operations.

Every operation uses argument-list subprocess calls (never a shell and never a
process-wide ``chdir``).  User-selected destinations are written transactionally:
FFmpeg writes a unique sibling file and the destination is replaced only after
the result has been validated.
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
from fractions import Fraction
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class VideoProcessor:
    """Probe and transform video files through FFmpeg/FFprobe."""

    SOFT_SUBTITLE_CODECS = {
        "mp4": "mov_text",
        "mov": "mov_text",
        "mkv": "srt",  # changed to ASS below when the input is ASS/SSA
        "webm": "webvtt",
    }
    _AUDIO_CODECS = {
        "wav": "pcm_s16le",
        "flac": "flac",
        "mp3": "libmp3lame",
        "m4a": "aac",
        "aac": "aac",
        "ogg": "libvorbis",
        "opus": "libopus",
    }

    def __init__(
        self,
        temp_dir: str | os.PathLike[str] | None = None,
        *,
        ffmpeg_path: str = "ffmpeg",
        ffprobe_path: str = "ffprobe",
    ) -> None:
        self.temp_dir = Path(temp_dir or tempfile.gettempdir()).expanduser().resolve()
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self.ffmpeg_path = ffmpeg_path
        self.ffprobe_path = ffprobe_path

    def get_video_info(self, video_path: str | os.PathLike[str]) -> dict[str, Any]:
        """Return stable media metadata, or an ``error`` entry on failure."""

        source = Path(video_path).expanduser().resolve()
        try:
            if not source.is_file():
                raise FileNotFoundError(f"Video file not found: {source}")
            probe = self._probe(source)
            streams = probe.get("streams", [])
            format_info = probe.get("format", {})
            video_info = next(
                (stream for stream in streams if stream.get("codec_type") == "video"),
                None,
            )
            audio_info = next(
                (stream for stream in streams if stream.get("codec_type") == "audio"),
                None,
            )
            duration = self._number(format_info.get("duration"), 0.0)
            if not duration and video_info:
                duration = self._number(video_info.get("duration"), 0.0)

            result: dict[str, Any] = {
                "filename": source.name,
                "format": format_info.get("format_name", "unknown"),
                "duration": duration,
                "size": int(self._number(format_info.get("size"), source.stat().st_size)),
                "bit_rate": self._optional_int(format_info.get("bit_rate")),
                "has_video": video_info is not None,
                "has_audio": audio_info is not None,
            }
            if video_info:
                result.update(
                    {
                        "video_codec": video_info.get("codec_name", "unknown"),
                        "width": int(self._number(video_info.get("width"), 0)),
                        "height": int(self._number(video_info.get("height"), 0)),
                        "fps": self._parse_frame_rate(
                            str(
                                video_info.get("avg_frame_rate")
                                or video_info.get("r_frame_rate")
                                or "0/1"
                            )
                        ),
                    }
                )
            if audio_info:
                result.update(
                    {
                        "audio_codec": audio_info.get("codec_name", "unknown"),
                        "audio_channels": int(self._number(audio_info.get("channels"), 0)),
                        "audio_sample_rate": int(
                            self._number(audio_info.get("sample_rate"), 0)
                        ),
                    }
                )
            return result
        except Exception as exc:
            logger.error("Could not probe video %s: %s", source, exc)
            return {"error": str(exc)}

    @staticmethod
    def _parse_frame_rate(frame_rate: str) -> float:
        try:
            value = float(Fraction(frame_rate))
            return round(value, 3) if value > 0 else 0.0
        except (ValueError, ZeroDivisionError):
            return 0.0

    def generate_thumbnail(
        self,
        video_path: str | os.PathLike[str],
        time_pos: float | None = None,
        width: int = 320,
    ) -> str | None:
        """Create a unique JPEG thumbnail and return its path."""

        source = Path(video_path).expanduser().resolve()
        if width < 16 or width > 8192:
            logger.error("Invalid thumbnail width: %s", width)
            return None
        if time_pos is None:
            info = self.get_video_info(source)
            if "error" in info:
                return None
            time_pos = float(info.get("duration", 0) or 0) / 2
        destination = self._unique_path(self.temp_dir, "thumb-", ".jpg")
        try:
            command = [
                self.ffmpeg_path,
                "-hide_banner",
                "-nostdin",
                "-loglevel",
                "error",
                "-ss",
                str(max(0.0, float(time_pos))),
                "-i",
                str(source),
                "-frames:v",
                "1",
                "-vf",
                f"scale={int(width)}:-2",
                "-q:v",
                "3",
                "-y",
                str(destination),
            ]
            self._run(command)
            if destination.is_file() and destination.stat().st_size > 0:
                return str(destination)
        except Exception as exc:
            logger.error("Could not create thumbnail for %s: %s", source, exc)
        self._remove(destination)
        return None

    def extract_audio(
        self,
        video_path: str | os.PathLike[str],
        output_path: str | os.PathLike[str] | None = None,
        format: str = "wav",
        sample_rate: int = 16000,
    ) -> str | None:
        """Extract mono audio without exposing a partial destination."""

        source = Path(video_path).expanduser().resolve()
        audio_format = str(format).lower().lstrip(".")
        codec = self._AUDIO_CODECS.get(audio_format)
        if codec is None or not 8000 <= int(sample_rate) <= 384000:
            logger.error("Unsupported audio export settings: %s/%s", audio_format, sample_rate)
            return None

        if output_path is None:
            destination = self._unique_path(
                self.temp_dir, "audio-", f".{audio_format}"
            )
            temporary = destination
            commit = False
        else:
            destination = Path(output_path).expanduser().resolve()
            if destination == source:
                logger.error("Refusing to replace the source video with extracted audio")
                return None
            destination.parent.mkdir(parents=True, exist_ok=True)
            temporary = self._unique_path(
                destination.parent, ".videotranslator-audio-", destination.suffix or f".{audio_format}"
            )
            commit = True
        try:
            command = [
                self.ffmpeg_path,
                "-hide_banner",
                "-nostdin",
                "-loglevel",
                "error",
                "-i",
                str(source),
                "-vn",
                "-map",
                "0:a:0",
                "-ac",
                "1",
                "-ar",
                str(int(sample_rate)),
                "-c:a",
                codec,
                "-y",
                str(temporary),
            ]
            self._run(command)
            if not temporary.is_file() or temporary.stat().st_size == 0:
                raise RuntimeError("FFmpeg did not create a valid audio file")
            if commit:
                os.replace(temporary, destination)
            return str(destination)
        except Exception as exc:
            logger.error("Could not extract audio from %s: %s", source, exc)
            self._remove(temporary)
            return None

    def extract_frames(
        self,
        video_path: str | os.PathLike[str],
        output_dir: str | os.PathLike[str] | None = None,
        fps: float = 1.0,
    ) -> str | None:
        """Extract frames into a unique directory (or a new requested directory)."""

        if not 0 < float(fps) <= 120:
            logger.error("Invalid frame extraction rate: %s", fps)
            return None
        source = Path(video_path).expanduser().resolve()
        if output_dir is None:
            destination = Path(
                tempfile.mkdtemp(prefix="videotranslator-frames-", dir=self.temp_dir)
            )
            staging = destination
            commit = False
        else:
            destination = Path(output_dir).expanduser().resolve()
            if destination.exists():
                logger.error("Refusing to overwrite frame directory: %s", destination)
                return None
            destination.parent.mkdir(parents=True, exist_ok=True)
            staging = Path(
                tempfile.mkdtemp(
                    prefix=".videotranslator-frames-", dir=destination.parent
                )
            )
            commit = True
        try:
            self._run(
                [
                    self.ffmpeg_path,
                    "-hide_banner",
                    "-nostdin",
                    "-loglevel",
                    "error",
                    "-i",
                    str(source),
                    "-vf",
                    f"fps={float(fps):g}",
                    "-start_number",
                    "0",
                    "-y",
                    str(staging / "frame_%06d.jpg"),
                ]
            )
            if not any(staging.glob("frame_*.jpg")):
                raise RuntimeError("FFmpeg did not extract any frames")
            if commit:
                os.replace(staging, destination)
            return str(destination)
        except Exception as exc:
            logger.error("Could not extract frames from %s: %s", source, exc)
            shutil.rmtree(staging, ignore_errors=True)
            return None

    def add_subtitles_to_video(
        self,
        video_path: str,
        subtitle_path: str,
        output_path: str,
        font: str = "Arial",
        font_size: int = 24,
        font_color: str = "white",
        position: str = "bottom",
    ) -> bool:
        """Compatibility alias for hard subtitle rendering."""

        del font
        return self.burn_subtitles_to_video(
            video_path,
            subtitle_path,
            output_path,
            font_size=font_size,
            font_color=font_color,
            position=position,
        )

    def embed_subtitles_to_video(
        self,
        video_path: str,
        subtitle_path: str,
        output_path: str,
        subtitle_lang: str = "und",
    ) -> bool:
        """Mux a selectable subtitle track using a container-compatible codec."""

        source = Path(video_path).expanduser().resolve()
        subtitle = Path(subtitle_path).expanduser().resolve()
        destination = Path(output_path).expanduser().resolve()
        container = destination.suffix.lower().lstrip(".")
        subtitle_format = subtitle.suffix.lower().lstrip(".")
        codec = self.SOFT_SUBTITLE_CODECS.get(container)
        if container == "mkv":
            codec = "ass" if subtitle_format in {"ass", "ssa"} else "srt"
        if codec is None:
            logger.error("Container %s has no supported soft-subtitle contract", container)
            return False
        if not source.is_file() or not subtitle.is_file() or destination == source:
            logger.error("Invalid source, subtitle, or destination for subtitle embedding")
            return False

        temporary = self._output_temp(destination)
        try:
            command = self._soft_subtitle_command(
                source,
                subtitle,
                temporary,
                container,
                codec,
                subtitle_lang,
            )
            self._run(command)
            self._validate_video(temporary, require_subtitle=True)
            os.replace(temporary, destination)
            return True
        except Exception as exc:
            logger.error("Could not embed subtitles in %s: %s", source, exc)
            self._remove(temporary)
            return False

    def burn_subtitles_to_video(
        self,
        video_path: str,
        subtitle_path: str,
        output_path: str,
        font_size: int = 24,
        font_color: str = "white",
        position: str = "bottom",
    ) -> bool:
        """Render subtitles into the video without changing the process cwd."""

        del font_size, font_color, position
        source = Path(video_path).expanduser().resolve()
        subtitle = Path(subtitle_path).expanduser().resolve()
        destination = Path(output_path).expanduser().resolve()
        if not source.is_file() or not subtitle.is_file() or destination == source:
            logger.error("Invalid source, subtitle, or destination for hard subtitles")
            return False
        filter_name = "ass" if subtitle.suffix.lower() in {".ass", ".ssa"} else "subtitles"
        if not self.check_subtitle_filter_available(self.ffmpeg_path, filter_name):
            logger.error(
                "FFmpeg filter '%s' is unavailable; install an FFmpeg build with libass",
                filter_name,
            )
            return False

        temporary = self._output_temp(destination)
        try:
            with tempfile.TemporaryDirectory(
                prefix="videotranslator-subtitles-", dir=self.temp_dir
            ) as workspace:
                local_subtitle = Path(workspace) / f"subtitle{subtitle.suffix.lower()}"
                shutil.copyfile(subtitle, local_subtitle)
                command = self._hard_subtitle_command(
                    source,
                    local_subtitle.name,
                    temporary,
                    destination.suffix.lower().lstrip("."),
                    filter_name,
                )
                self._run(command, cwd=Path(workspace))
            self._validate_video(temporary)
            os.replace(temporary, destination)
            return True
        except Exception as exc:
            logger.error("Could not burn subtitles into %s: %s", source, exc)
            self._remove(temporary)
            return False

    # Historical private entry points now share the safe implementation.
    def _burn_subtitles_direct(
        self, video_path: str, subtitle_path: str, output_path: str
    ) -> bool:
        return self.burn_subtitles_to_video(video_path, subtitle_path, output_path)

    def _burn_subtitles_fallback(
        self,
        video_path: str,
        subtitle_path: str,
        output_path: str,
        font_size: int = 24,
        font_color: str = "white",
    ) -> bool:
        return self.burn_subtitles_to_video(
            video_path,
            subtitle_path,
            output_path,
            font_size=font_size,
            font_color=font_color,
        )

    @classmethod
    def check_ffmpeg_available(cls, ffmpeg_path: str = "ffmpeg") -> bool:
        try:
            result = subprocess.run(
                [ffmpeg_path, "-version"],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=10,
                check=False,
            )
            return result.returncode == 0
        except (OSError, subprocess.SubprocessError):
            return False

    @classmethod
    def ffmpeg_filter_names(cls, ffmpeg_path: str = "ffmpeg") -> set[str]:
        """Return FFmpeg filter names without importing or guessing build flags."""

        try:
            result = subprocess.run(
                [ffmpeg_path, "-hide_banner", "-filters"],
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            return set()
        names: set[str] = set()
        for line in f"{result.stdout}\n{result.stderr}".splitlines():
            fields = line.split()
            if (
                len(fields) >= 2
                and fields[1] != "="
                and re.fullmatch(r"[.A-Z|]{2,4}", fields[0])
            ):
                names.add(fields[1])
        return names

    @classmethod
    def check_subtitle_filter_available(
        cls, ffmpeg_path: str = "ffmpeg", filter_name: str = "subtitles"
    ) -> bool:
        return filter_name in cls.ffmpeg_filter_names(ffmpeg_path)

    def _probe(self, path: Path) -> dict[str, Any]:
        result = self._run(
            [
                self.ffprobe_path,
                "-v",
                "error",
                "-show_format",
                "-show_streams",
                "-of",
                "json",
                str(path),
            ],
            timeout=30,
        )
        try:
            return json.loads(result.stdout or "{}")
        except json.JSONDecodeError as exc:
            raise RuntimeError("FFprobe returned invalid JSON") from exc

    def _validate_video(self, path: Path, *, require_subtitle: bool = False) -> None:
        if not path.is_file() or path.stat().st_size == 0:
            raise RuntimeError("FFmpeg did not create a valid output file")
        probe = self._probe(path)
        stream_types = {stream.get("codec_type") for stream in probe.get("streams", [])}
        if "video" not in stream_types:
            raise RuntimeError("Output contains no video stream")
        if require_subtitle and "subtitle" not in stream_types:
            raise RuntimeError("Output contains no subtitle stream")

    def validate_video_output(
        self,
        path: str | os.PathLike[str],
        *,
        require_subtitle: bool = False,
    ) -> None:
        """Validate a completed video before exposing it as a successful export."""

        self._validate_video(
            Path(path).expanduser().resolve(), require_subtitle=require_subtitle
        )

    def _soft_subtitle_command(
        self,
        source: Path,
        subtitle: Path,
        output: Path,
        container: str,
        subtitle_codec: str,
        language: str,
    ) -> list[str]:
        command = [
            self.ffmpeg_path,
            "-hide_banner",
            "-nostdin",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(source),
            "-i",
            str(subtitle),
            "-map",
            "0:v:0",
            "-map",
            "0:a?",
            "-map",
            "1:0",
            "-map_metadata",
            "0",
        ]
        if container in {"mp4", "mov"}:
            command.extend(["-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-c:a", "aac"])
        elif container == "webm":
            command.extend(["-c:v", "libvpx-vp9", "-crf", "30", "-b:v", "0", "-c:a", "libopus"])
        else:  # Matroska is designed to carry the original elementary streams.
            command.extend(["-c:v", "copy", "-c:a", "copy"])
        command.extend(
            [
                "-c:s",
                subtitle_codec,
                "-metadata:s:s:0",
                f"language={self._metadata_language(language)}",
                str(output),
            ]
        )
        return command

    def _hard_subtitle_command(
        self,
        source: Path,
        subtitle_name: str,
        output: Path,
        container: str,
        filter_name: str,
    ) -> list[str]:
        command = [
            self.ffmpeg_path,
            "-hide_banner",
            "-nostdin",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(source),
            "-vf",
            f"{filter_name}=filename={subtitle_name}",
            "-map",
            "0:v:0",
            "-map",
            "0:a?",
            "-map_metadata",
            "0",
        ]
        if container == "webm":
            command.extend(["-c:v", "libvpx-vp9", "-crf", "30", "-b:v", "0", "-c:a", "libopus"])
        else:
            command.extend(["-c:v", "libx264", "-preset", "medium", "-crf", "20", "-c:a", "copy"])
        command.append(str(output))
        return command

    def _output_temp(self, destination: Path) -> Path:
        destination.parent.mkdir(parents=True, exist_ok=True)
        return self._unique_path(
            destination.parent,
            ".videotranslator-video-",
            destination.suffix or ".mkv",
        )

    @staticmethod
    def _unique_path(directory: Path, prefix: str, suffix: str) -> Path:
        descriptor, value = tempfile.mkstemp(prefix=prefix, suffix=suffix, dir=directory)
        os.close(descriptor)
        return Path(value)

    @staticmethod
    def _metadata_language(language: str) -> str:
        primary = str(language).lower().replace("_", "-").split("-", 1)[0]
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

    @staticmethod
    def _number(value: Any, default: float) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    @classmethod
    def _optional_int(cls, value: Any) -> int | None:
        try:
            return int(cls._number(value, 0)) if value is not None else None
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _remove(path: Path) -> None:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            logger.warning("Could not remove temporary media file: %s", path)

    @staticmethod
    def _run(
        command: list[str],
        *,
        cwd: Path | None = None,
        timeout: int = 120,
    ) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            command,
            cwd=str(cwd) if cwd else None,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "no error details")[-4000:].strip()
            raise RuntimeError(
                f"{Path(command[0]).name} exited with code {result.returncode}: {detail}"
            )
        return result
