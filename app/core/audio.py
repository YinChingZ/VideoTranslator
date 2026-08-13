#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Enhanced audio processing module for video translation system.
优化的音频处理模块，支持流式处理和内存优化
"""

import gc
import logging
import os
import tempfile
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import ffmpeg
import numpy as np

logger = logging.getLogger(__name__)


class AudioProcessingError(Exception):
    """音频处理相关异常"""
    pass


class AudioProcessor:
    """优化的音频处理类，支持流式处理和内存管理"""
    
    def __init__(self, temp_dir: Optional[Path] = None, max_memory_mb: int = 512):
        """
        初始化音频处理器
        
        Args:
            temp_dir: 临时文件目录，如未提供则使用系统临时目录
            max_memory_mb: 最大内存使用限制（MB）
        """
        self.temp_dir = temp_dir or Path(tempfile.gettempdir()) / "videotranslator_audio"
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self.max_memory_mb = max_memory_mb
        self.temp_files: List[Path] = []
        
        logger.info(f"音频处理器初始化: temp_dir={self.temp_dir}, max_memory={max_memory_mb}MB")
    
    @contextmanager
    def _temp_file(self, suffix: str = ".wav"):
        """创建临时文件的上下文管理器"""
        temp_path = self.temp_dir / f"temp_{uuid.uuid4().hex}{suffix}"
        self.temp_files.append(temp_path)
        try:
            yield temp_path
        finally:
            if temp_path.exists():
                try:
                    temp_path.unlink()
                    self.temp_files.remove(temp_path)
                except Exception as e:
                    logger.warning(f"清理临时文件失败: {temp_path} - {e}")
    
    def cleanup(self):
        """清理所有临时文件"""
        for temp_file in self.temp_files[:]:
            try:
                if temp_file.exists():
                    temp_file.unlink()
                self.temp_files.remove(temp_file)
            except Exception as e:
                logger.warning(f"清理临时文件失败: {temp_file} - {e}")
        
        # 强制垃圾回收
        gc.collect()

    @staticmethod
    def _reserve_sibling(destination: Path, suffix: str) -> Path:
        """Reserve a unique sibling for an atomic user-visible file commit."""

        descriptor, value = tempfile.mkstemp(
            prefix=".videotranslator-audio-",
            suffix=suffix,
            dir=destination.parent,
        )
        os.close(descriptor)
        return Path(value)

    @staticmethod
    def _remove_file(path: Path) -> None:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            logger.warning("无法清理临时音频文件: %s", path)
    
    def extract_audio_from_video(self, video_path: Union[str, Path], 
                               output_path: Optional[Union[str, Path]] = None, 
                               format: str = 'wav', sample_rate: int = 16000,
                               channels: int = 1) -> Optional[Path]:
        """
        从视频中提取音频（内存优化版本）
        
        Args:
            video_path: 视频文件路径
            output_path: 音频输出路径，如未提供则生成临时文件
            format: 音频格式，默认为wav（适合语音识别）
            sample_rate: 采样率，默认16kHz（适合语音识别）
            channels: 声道数，默认1（单声道）
            
        Returns:
            音频文件路径，失败则返回None
        """
        video_path = Path(video_path).expanduser().resolve()
        if not video_path.exists():
            raise AudioProcessingError(f"视频文件不存在: {video_path}")

        audio_format = str(format).lower().lstrip('.')
        commit_output = output_path is not None
        if commit_output:
            destination = Path(output_path).expanduser().resolve()
            if destination == video_path:
                raise AudioProcessingError("拒绝用提取的音频覆盖源视频")
            destination.parent.mkdir(parents=True, exist_ok=True)
            staging = self._reserve_sibling(
                destination, destination.suffix or f".{audio_format}"
            )
        else:
            destination = self.temp_dir / f"audio_{uuid.uuid4().hex}.{audio_format}"
            staging = destination

        try:
            # 使用ffmpeg直接流式处理，避免加载整个文件到内存
            stream = ffmpeg.input(str(video_path))
            # 直接设置音频参数，避免复杂的滤镜链
            out = ffmpeg.output(
                stream.audio,
                str(staging),
                acodec='pcm_s16le',  # 使用PCM编码
                ac=channels,         # 声道数
                ar=sample_rate,      # 采样率
                format=audio_format
            )
            
            # 运行ffmpeg命令
            ffmpeg.run(out, overwrite_output=True, quiet=True)
            
            if not staging.is_file() or staging.stat().st_size == 0:
                raise AudioProcessingError("音频提取失败，输出文件不存在")

            if commit_output:
                os.replace(staging, destination)
            logger.info(f"成功提取音频: {video_path} -> {destination}")
            return destination
                
        except ffmpeg.Error as e:
            error_msg = e.stderr.decode() if e.stderr else str(e)
            logger.error(f"FFmpeg音频提取失败: {error_msg}")
            self._remove_file(staging)
            raise AudioProcessingError(f"FFmpeg错误: {error_msg}")
        except Exception as e:
            logger.error(f"音频提取失败: {e}")
            self._remove_file(staging)
            if isinstance(e, AudioProcessingError):
                raise
            raise AudioProcessingError(f"音频提取失败: {e}")
    
    def preprocess_audio_for_speech(self, audio_path: Union[str, Path], 
                                  output_path: Optional[Union[str, Path]] = None,
                                  target_sample_rate: int = 16000,
                                  noise_reduction: bool = True,
                                  normalize: bool = True) -> Optional[Path]:
        """
        为语音识别预处理音频（内存优化版本）
        
        Args:
            audio_path: 输入音频文件路径
            output_path: 输出音频文件路径
            target_sample_rate: 目标采样率
            noise_reduction: 是否进行降噪处理
            normalize: 是否进行音量归一化
            
        Returns:
            处理后的音频文件路径，失败则返回None
        """
        audio_path = Path(audio_path).expanduser().resolve()
        if not audio_path.exists():
            raise AudioProcessingError(f"音频文件不存在: {audio_path}")

        commit_output = output_path is not None
        if commit_output:
            destination = Path(output_path).expanduser().resolve()
            if destination == audio_path:
                raise AudioProcessingError("拒绝用预处理结果覆盖源音频")
            destination.parent.mkdir(parents=True, exist_ok=True)
            staging = self._reserve_sibling(destination, destination.suffix or ".wav")
        else:
            destination = self.temp_dir / f"processed_{uuid.uuid4().hex}.wav"
            staging = destination

        try:
            try:
                import soundfile as sf
            except ImportError as exc:
                raise AudioProcessingError(
                    "保存预处理音频需要 soundfile；请安装 soundfile "
                    "（librosa 0.10+ 使用它替代已移除的 librosa.output.write_wav）"
                ) from exc

            staging.parent.mkdir(parents=True, exist_ok=True)

            # Stream processed chunks directly to disk.  This avoids both the
            # removed librosa.output.write_wav API and concatenating the full
            # recording back into memory after chunk processing.
            wrote_audio = False
            with self._process_audio_chunks(audio_path, target_sample_rate) as processor:
                with sf.SoundFile(
                    str(staging),
                    mode="w",
                    samplerate=target_sample_rate,
                    channels=1,
                    format="WAV",
                    subtype="PCM_16",
                ) as output_file:
                    for chunk_data, sr in processor:
                        if noise_reduction:
                            chunk_data = self._apply_noise_reduction(chunk_data, sr)

                        if normalize:
                            chunk_data = self._normalize_audio(chunk_data)

                        output_file.write(np.asarray(chunk_data, dtype=np.float32))
                        wrote_audio = True

            if wrote_audio:
                if not staging.is_file() or staging.stat().st_size == 0:
                    raise AudioProcessingError("音频预处理未生成有效文件")
                if commit_output:
                    os.replace(staging, destination)
                logger.info(f"音频预处理完成: {audio_path} -> {destination}")
                return destination

            self._remove_file(staging)
            
        except Exception as e:
            logger.error(f"音频预处理失败: {e}")
            self._remove_file(staging)
            if isinstance(e, AudioProcessingError):
                raise
            raise AudioProcessingError(f"音频预处理失败: {e}")
        
        return None
    
    @contextmanager
    def _process_audio_chunks(self, audio_path: Path, target_sr: int, chunk_duration: float = 30.0):
        """音频分块处理的上下文管理器"""
        audio_file = None
        try:
            try:
                import soundfile as sf
            except ImportError as exc:
                raise AudioProcessingError(
                    "流式音频处理需要 soundfile；请安装 soundfile"
                ) from exc

            audio_file = sf.SoundFile(str(audio_path), mode="r")
            sr = audio_file.samplerate
            chunk_size = max(1, int(chunk_duration * sr))

            def chunk_generator():
                while True:
                    chunk = audio_file.read(
                        frames=chunk_size,
                        dtype="float32",
                        always_2d=False,
                    )
                    if chunk.size == 0:
                        break

                    # Whisper expects mono audio.  Average channels instead of
                    # silently selecting only one side of a stereo recording.
                    if chunk.ndim > 1:
                        chunk = np.mean(chunk, axis=1)

                    if sr != target_sr:
                        try:
                            import librosa
                        except ImportError as exc:
                            raise AudioProcessingError(
                                "重采样音频需要 librosa；请安装 librosa"
                            ) from exc
                        chunk = librosa.resample(chunk, orig_sr=sr, target_sr=target_sr)
                    yield chunk, target_sr

            yield chunk_generator()
        finally:
            if audio_file is not None:
                audio_file.close()
            gc.collect()
    
    def _apply_noise_reduction(self, audio_data: np.ndarray, sample_rate: int) -> np.ndarray:
        """应用基础降噪处理"""
        try:
            # 使用简单的高通滤波器移除低频噪音
            from scipy.signal import butter, filtfilt
            
            # 设计高通滤波器 (截止频率80Hz)
            nyquist = sample_rate / 2
            cutoff = 80 / nyquist
            b, a = butter(4, cutoff, btype='high')
            
            # 应用滤波器
            filtered = filtfilt(b, a, audio_data)
            return filtered
            
        except ImportError:
            logger.warning("scipy未安装，跳过降噪处理")
            return audio_data
        except Exception as e:
            logger.warning(f"降噪处理失败: {e}")
            return audio_data
    
    def _normalize_audio(self, audio_data: np.ndarray, target_db: float = -20.0) -> np.ndarray:
        """音频音量归一化"""
        try:
            # 计算RMS
            rms = np.sqrt(np.mean(audio_data ** 2))
            if rms > 0:
                # 计算增益
                target_rms = 10 ** (target_db / 20)
                gain = target_rms / rms
                # 应用增益，避免削波
                normalized = audio_data * min(gain, 1.0)
                return normalized
            
        except Exception as e:
            logger.warning(f"音频归一化失败: {e}")
        
        return audio_data
    
    def split_audio_by_silence(self, audio_path: Union[str, Path], 
                             output_dir: Optional[Union[str, Path]] = None,
                             min_silence_len: int = 500, 
                             silence_thresh: int = -40,
                             keep_silence: int = 300,
                             max_segment_length: int = 30000) -> List[Path]:
        """
        通过静音检测将音频分割成多个片段（内存优化版本）
        
        Args:
            audio_path: 音频文件路径
            output_dir: 输出目录，如未提供则创建临时目录
            min_silence_len: 最小静音长度（毫秒）
            silence_thresh: 静音阈值（dBFS）
            keep_silence: 保留的静音长度（毫秒）
            max_segment_length: 最大段落长度（毫秒）
            
        Returns:
            分割后的音频片段文件列表
        """
        audio_path = Path(audio_path)
        if not audio_path.exists():
            raise AudioProcessingError(f"音频文件不存在: {audio_path}")
        
        try:
            try:
                from pydub import AudioSegment
                from pydub.silence import split_on_silence
            except ImportError as exc:
                raise AudioProcessingError(
                    "按静音分割音频需要 pydub；请安装媒体增强依赖"
                ) from exc

            if output_dir is None:
                output_dir = self.temp_dir / f"segments_{uuid.uuid4().hex}"
            else:
                output_dir = Path(output_dir)
            
            output_dir.mkdir(parents=True, exist_ok=True)
            
            # 使用pydub进行静音检测，但分块处理避免内存问题
            audio = AudioSegment.from_file(str(audio_path))
            
            # 检测静音分割点
            chunks = split_on_silence(
                audio,
                min_silence_len=min_silence_len,
                silence_thresh=silence_thresh,
                keep_silence=keep_silence
            )
            
            # 合并过短的片段并限制最大长度
            processed_chunks = self._optimize_chunks(chunks, max_segment_length)
            
            # 导出片段
            segment_files = []
            for i, chunk in enumerate(processed_chunks):
                segment_file = output_dir / f"segment_{i:04d}.wav"
                chunk.export(str(segment_file), format="wav")
                segment_files.append(segment_file)
                
                logger.debug(f"导出音频片段: {segment_file} (时长: {len(chunk)/1000:.2f}秒)")
            
            logger.info(f"音频分割完成: {len(segment_files)}个片段")
            return segment_files
            
        except Exception as e:
            logger.error(f"音频分割失败: {e}")
            raise AudioProcessingError(f"音频分割失败: {e}")
    
    def _optimize_chunks(self, chunks: List[Any],
                        max_length: int, min_length: int = 1000) -> List[Any]:
        """优化音频片段长度"""
        if not chunks:
            return []
        
        optimized = []
        current_chunk = chunks[0]
        
        for next_chunk in chunks[1:]:
            # 如果当前块太短，与下一块合并
            if len(current_chunk) < min_length:
                current_chunk += next_chunk
            # 如果合并后仍然不超过最大长度
            elif len(current_chunk) + len(next_chunk) <= max_length:
                current_chunk += next_chunk
            else:
                # 当前块已经足够长，保存并开始新块
                optimized.append(current_chunk)
                current_chunk = next_chunk
        
        # 添加最后一块
        if current_chunk:
            optimized.append(current_chunk)
        
        return optimized
    
    def get_audio_info(self, audio_path: Union[str, Path]) -> Dict[str, Any]:
        """获取音频文件信息（不加载整个文件）"""
        audio_path = Path(audio_path)
        if not audio_path.exists():
            raise AudioProcessingError(f"音频文件不存在: {audio_path}")
        
        try:
            # 使用ffprobe获取音频信息，避免加载文件
            probe = ffmpeg.probe(str(audio_path))
            audio_stream = next(
                stream for stream in probe['streams'] 
                if stream['codec_type'] == 'audio'
            )
            
            return {
                'duration': float(audio_stream.get('duration', 0)),
                'sample_rate': int(audio_stream.get('sample_rate', 0)),
                'channels': int(audio_stream.get('channels', 0)),
                'codec': audio_stream.get('codec_name', 'unknown'),
                'bitrate': int(audio_stream.get('bit_rate', 0)),
                'file_size': audio_path.stat().st_size
            }
            
        except Exception as e:
            logger.error(f"获取音频信息失败: {e}")
            raise AudioProcessingError(f"获取音频信息失败: {e}")
    
    def __del__(self):
        """析构函数，清理临时文件"""
        try:
            self.cleanup()
        except Exception:
            pass  # 忽略析构函数中的异常
