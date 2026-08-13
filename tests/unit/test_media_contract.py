"""Executable contracts for probing and exporting real media."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from app.core.subtitle import SubtitleProcessor, SubtitleSegment
from app.core.video import VideoProcessor
from app.gui.video_export_thread import VideoExportWorker

pytestmark = pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="FFmpeg and FFprobe are required",
)


@pytest.fixture(scope="module")
def sample_media(tmp_path_factory):
    workspace = tmp_path_factory.mktemp("媒体 sample with spaces")
    source = workspace / "源 视频.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-nostdin",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=size=160x90:rate=12:duration=0.6",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:sample_rate=48000:duration=0.6",
            "-shortest",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-y",
            str(source),
        ],
        check=True,
    )
    return workspace, source


def _probe(path: Path) -> dict:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_streams",
            "-of",
            "json",
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def _subtitle_processor() -> SubtitleProcessor:
    processor = SubtitleProcessor()
    processor.segments = [
        SubtitleSegment(0.0, 0.45, "Hello, world", "你好，世界", index=1)
    ]
    return processor


def test_probe_thumbnail_audio_and_frames_support_unicode_paths(sample_media):
    workspace, source = sample_media
    processor = VideoProcessor(temp_dir=workspace)

    info = processor.get_video_info(source)
    assert "error" not in info
    assert info["filename"] == "源 视频.mp4"
    assert info["has_video"] is True
    assert info["has_audio"] is True
    assert info["width"] == 160 and info["height"] == 90
    assert 0.4 <= info["duration"] <= 1.0
    assert 11.5 <= info["fps"] <= 12.5

    first_thumbnail = Path(processor.generate_thumbnail(source, width=96))
    second_thumbnail = Path(processor.generate_thumbnail(source, width=96))
    assert first_thumbnail != second_thumbnail
    assert first_thumbnail.read_bytes().startswith(b"\xff\xd8")

    audio = workspace / "抽取 音频.wav"
    assert processor.extract_audio(source, audio, sample_rate=16000) == str(audio)
    audio_streams = _probe(audio)["streams"]
    assert audio_streams[0]["codec_type"] == "audio"
    assert audio_streams[0]["sample_rate"] == "16000"
    assert audio_streams[0]["channels"] == 1

    frames = workspace / "抽帧 目录"
    assert processor.extract_frames(source, frames, fps=4) == str(frames)
    assert list(frames.glob("frame_*.jpg"))


def test_failed_audio_extract_preserves_existing_destination(sample_media):
    workspace, _source = sample_media
    destination = workspace / "existing 音频.wav"
    destination.write_bytes(b"keep-this")

    result = VideoProcessor(temp_dir=workspace).extract_audio(
        workspace / "missing.mp4", destination
    )

    assert result is None
    assert destination.read_bytes() == b"keep-this"
    assert not list(workspace.glob(".videotranslator-audio-*"))


@pytest.mark.parametrize(
    ("container", "expected_codec", "preserves_language"),
    [
        ("mp4", "mov_text", True),
        ("mov", "mov_text", False),
        ("mkv", "subrip", True),
        ("webm", "webvtt", True),
    ],
)
def test_soft_subtitle_container_contracts(
    sample_media, tmp_path, container, expected_codec, preserves_language
):
    _workspace, source = sample_media
    subtitle = tmp_path / "字幕 file.srt"
    _subtitle_processor().save_to_file(
        str(subtitle), "srt", language_mode="bilingual"
    )
    output = tmp_path / f"导出 result.{container}"

    assert VideoProcessor(temp_dir=tmp_path).embed_subtitles_to_video(
        str(source), str(subtitle), str(output), subtitle_lang="zh-CN"
    )

    subtitle_stream = next(
        stream
        for stream in _probe(output)["streams"]
        if stream["codec_type"] == "subtitle"
    )
    assert subtitle_stream["codec_name"] == expected_codec
    if preserves_language:
        assert subtitle_stream.get("tags", {}).get("language") == "zho"


def test_unsupported_soft_subtitle_container_preserves_destination(
    sample_media, tmp_path
):
    _workspace, source = sample_media
    subtitle = tmp_path / "subtitle.srt"
    subtitle.write_text("1\n00:00:00,000 --> 00:00:00,400\nHello\n", encoding="utf-8")
    output = tmp_path / "existing.avi"
    output.write_bytes(b"keep-this")

    assert not VideoProcessor(temp_dir=tmp_path).embed_subtitles_to_video(
        str(source), str(subtitle), str(output)
    )
    assert output.read_bytes() == b"keep-this"


def test_hard_subtitle_capability_matches_real_filter_list(sample_media, tmp_path):
    _workspace, source = sample_media
    processor = VideoProcessor(temp_dir=tmp_path)
    filters = processor.ffmpeg_filter_names()
    subtitle = tmp_path / "hard subtitle.srt"
    subtitle.write_text(
        "1\n00:00:00,000 --> 00:00:00,400\nHard subtitle\n",
        encoding="utf-8",
    )
    output = tmp_path / "hard output.mp4"

    success = processor.burn_subtitles_to_video(
        str(source), str(subtitle), str(output)
    )

    assert processor.check_subtitle_filter_available() == ("subtitles" in filters)
    if "subtitles" in filters:
        assert success is True
        assert output.is_file()
    else:
        assert success is False
        assert not output.exists()


def test_core_media_operations_never_change_process_working_directory(
    sample_media, tmp_path
):
    _workspace, source = sample_media
    original_cwd = os.getcwd()
    subtitle = tmp_path / "subtitle.srt"
    subtitle.write_text(
        "1\n00:00:00,000 --> 00:00:00,400\nHello\n", encoding="utf-8"
    )
    processor = VideoProcessor(temp_dir=tmp_path)

    processor.generate_thumbnail(source)
    processor.embed_subtitles_to_video(
        str(source), str(subtitle), str(tmp_path / "subtitled.mkv")
    )
    processor.burn_subtitles_to_video(
        str(source), str(subtitle), str(tmp_path / "burned.mp4")
    )

    assert os.getcwd() == original_cwd


def test_export_worker_rejects_hard_subtitles_before_spawning_when_filter_missing(
    sample_media, tmp_path, monkeypatch
):
    _workspace, source = sample_media
    worker = VideoExportWorker(
        {
            "output_dir": str(tmp_path),
            "filename": "hardcoded",
            "format": "srt",
            "language_option": "translation_only",
            "hardcode_subtitles": True,
            "video_path": str(source),
            "video_format": "mp4",
            "subtitle_data": [
                {
                    "start_time": 0.0,
                    "end_time": 0.4,
                    "original_text": "Hello",
                    "translated_text": "你好",
                }
            ],
        }
    )
    monkeypatch.setattr(
        VideoProcessor,
        "check_subtitle_filter_available",
        classmethod(lambda cls, ffmpeg_path="ffmpeg", filter_name="subtitles": False),
    )
    failures = []
    worker.failed.connect(failures.append)

    worker.run()

    assert len(failures) == 1
    assert "libass" in failures[0]
    assert not (tmp_path / "hardcoded.mp4").exists()
    assert not list(tmp_path.glob(".videotranslator-export-*"))


def test_subtitle_save_is_atomic_on_writer_failure(tmp_path, monkeypatch):
    destination = tmp_path / "existing.srt"
    destination.write_text("keep-this", encoding="utf-8")
    processor = _subtitle_processor()

    def fail_after_partial_write(output_path, language_mode):
        del language_mode
        Path(output_path).write_text("partial", encoding="utf-8")
        raise RuntimeError("simulated writer failure")

    monkeypatch.setattr(processor, "_save_srt", fail_after_partial_write)

    with pytest.raises(RuntimeError, match="simulated"):
        processor.save_to_file(str(destination), "srt")
    assert destination.read_text(encoding="utf-8") == "keep-this"
    assert not list(tmp_path.glob(".videotranslator-subtitle-*"))
