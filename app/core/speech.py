import gc
import inspect
import json
import logging
import os
import tempfile
import threading
import time
from typing import Any, Callable, Dict, Optional, Union

try:
    # ``openai-whisper`` exposes the top-level ``whisper`` package.  Do not
    # load a vendored source tree by path: clean installations do not contain
    # one, and doing so made importing this module fail before the application
    # could show a useful dependency error.
    import whisper
except ImportError as exc:  # pragma: no cover - depends on host environment
    whisper = None
    _WHISPER_IMPORT_ERROR = exc
else:
    _WHISPER_IMPORT_ERROR = None

try:
    import torch
except ImportError as exc:  # pragma: no cover - depends on host environment
    torch = None
    _TORCH_IMPORT_ERROR = exc
else:
    _TORCH_IMPORT_ERROR = None

from app.utils.memory_manager import MemoryMonitor, memory_managed_operation
from app.utils.paths import (
    ensure_private_directory,
    get_transcription_cache_dir,
    get_whisper_model_dir,
)


class SpeechRecognizer:
    """处理语音识别的类，使用OpenAI的Whisper模型"""
    
    def __init__(self, model: str = "base", device: Optional[str] = None, 
               compute_type: str = "float16"):
        """
        初始化语音识别器
        
        Args:
            model: Whisper模型类型 ('tiny', 'base', 'small', 'medium', 'large')
            device: 计算设备 ('cpu', 'cuda', None=auto)
            compute_type: 计算精度 ('float16', 'float32', 'int8')
        """
        self.model_name = model
        self.cancel_flag = False
        self.processing_thread = None
        
        # 初始化内存监控器
        self.memory_monitor = MemoryMonitor()
        
        # 确定设备（如果未指定）
        if device is None:
            device = "cuda" if self._cuda_available() else "cpu"
        self.device = device
        
        # 确定计算类型
        self.compute_type = compute_type
        if self.device == "cpu" and compute_type == "float16":
            # CPU不支持float16，降级到float32
            self.compute_type = "float32"
        
        self.model = None  # 延迟加载模型
        logging.info(f"初始化语音识别器: 模型={model}, 设备={device}, 计算类型={compute_type}")

    @staticmethod
    def _cuda_available() -> bool:
        """Return whether CUDA is available without requiring torch at import time."""
        return bool(torch is not None and torch.cuda.is_available())

    @staticmethod
    def _ensure_dependencies() -> None:
        """Raise an actionable error when speech dependencies are unavailable."""
        missing = []
        if whisper is None:
            missing.append("openai-whisper")
        if torch is None:
            missing.append("torch")

        if missing:
            details = []
            if _WHISPER_IMPORT_ERROR is not None:
                details.append(f"whisper: {_WHISPER_IMPORT_ERROR}")
            if _TORCH_IMPORT_ERROR is not None:
                details.append(f"torch: {_TORCH_IMPORT_ERROR}")
            detail_text = f" ({'; '.join(details)})" if details else ""
            raise RuntimeError(
                "Whisper 语音识别依赖不可用。请安装 "
                f"{', '.join(missing)}（例如运行 `pip install openai-whisper torch`）"
                f"{detail_text}"
            )
    
    def load_model(self):
        """加载Whisper模型"""
        if self.model is not None:
            return

        self._ensure_dependencies()
            
        try:
            logging.info(f"正在加载Whisper模型: {self.model_name}")
            load_start = time.time()
            
            # Wheels and application bundles may be installed read-only.
            # Whisper models therefore live in a platform cache, never beside
            # the source package.  An environment override supports managed
            # or large-volume model stores.
            models_dir = ensure_private_directory(get_whisper_model_dir())
            
            self.model = whisper.load_model(
                self.model_name,
                device=self.device,
                download_root=str(models_dir),
            )
            
            load_time = time.time() - load_start
            logging.info(f"Whisper模型加载完成，用时: {load_time:.2f}秒")
            
        except Exception as e:
            logging.error(f"加载Whisper模型失败: {str(e)}")
            raise
    
    def transcribe(self, audio_path: str, language: Optional[str] = None, 
                task: str = "transcribe", progress_callback: Optional[Callable[[int], None]] = None) -> Dict[str, Any]:
        """
        转写音频文件（支持内存管理和取消）
        
        Args:
            audio_path: 音频文件路径
            language: 音频语言代码（如'zh', 'en'），None表示自动检测
            task: 任务类型 ('transcribe' or 'translate')
            progress_callback: 进度回调函数，接收进度百分比(0-100)
            
        Returns:
            包含转写结果的字典，格式：
            {
                "text": "完整转写文本",
                "segments": [{"start": 0.0, "end": 5.0, "text": "segment文本"}],
                "language": "检测到的语言",
                "detected_language": "检测到的语言"
            }
        """
        with memory_managed_operation(max_memory_mb=2048):  # 2GB for speech recognition
            try:
                # 重置取消标志
                self.cancel_flag = False
                
                # 检查内存使用情况
                memory_stats = self.memory_monitor.get_memory_stats()
                if memory_stats.percent > 85:
                    logging.warning(f"内存使用率过高: {memory_stats.percent:.1f}%，建议释放内存后重试")
                
                # 加载模型（如果尚未加载）
                self.load_model()
                
                # 检查文件是否存在
                if not os.path.exists(audio_path):
                    raise FileNotFoundError(f"音频文件不存在: {audio_path}")
                
                logging.info(f"开始转写音频: {audio_path}")
                transcribe_start = time.time()
                
                # 设置转写选项
                options = {
                    "task": task,
                    "verbose": True,
                }
                
                if language:
                    options["language"] = language
                
                # 创建自定义进度回调
                if progress_callback:
                    progress_callback(0)
                    try:
                        parameters = inspect.signature(self.model.transcribe).parameters
                    except (TypeError, ValueError):
                        parameters = {}

                    # Upstream openai-whisper currently has no progress
                    # callback argument.  Some compatible backends do, so use
                    # it only when explicitly supported instead of passing an
                    # unknown decoding option to upstream Whisper.
                    if "progress_callback" in parameters:
                        original_callback = getattr(
                            self.model.transcribe, "__kwdefaults__", None
                        ) or {}
                        original_callback = original_callback.get("progress_callback")
                    
                        def wrapped_progress(progress: Union[float, dict]):
                            if self.cancel_flag:
                                return True

                            if isinstance(progress, float):
                                percent = int(progress * 100)
                            elif isinstance(progress, dict) and 'progress' in progress:
                                percent = int(progress['progress'] * 100)
                            else:
                                percent = 0

                            progress_callback(percent)
                            if original_callback:
                                original_callback(progress)
                            return False

                        options["progress_callback"] = wrapped_progress
                
                # 执行转写
                result = self.model.transcribe(audio_path, **options)

                if self.cancel_flag:
                    raise InterruptedError("语音识别已取消")
                if progress_callback:
                    progress_callback(100)
                
                transcribe_time = time.time() - transcribe_start
                logging.info(f"音频转写完成，用时: {transcribe_time:.2f}秒")
                
                # 提取关键信息
                output = {
                    "text": result["text"],
                    "segments": result["segments"],
                    "language": result.get("language", language),
                    "detected_language": result.get("detected_language", result.get("language", language))
                }
                
                # 强制垃圾回收
                gc.collect()
                if self._cuda_available():
                    torch.cuda.empty_cache()
                
                return output
                
            except Exception as e:
                # 出错时也要清理内存
                gc.collect()
                if self._cuda_available():
                    torch.cuda.empty_cache()
                logging.error(f"转写音频失败: {str(e)}")
                raise
    
    def process_segments(self, audio_path: str, segment_length: int = 30, 
                       language: Optional[str] = None, 
                       progress_callback: Optional[Callable[[int], None]] = None) -> Dict[str, Any]:
        """
        分段处理长音频文件
        
        Args:
            audio_path: 音频文件路径
            segment_length: 分段长度（秒）
            language: 音频语言代码
            progress_callback: 进度回调函数
            
        Returns:
            处理结果字典
        """
        try:
            import ffmpeg

            if segment_length <= 0:
                raise ValueError("segment_length 必须大于 0")

            # 加载模型（如果尚未加载）
            self.load_model()
            
            # 获取音频时长
            probe = ffmpeg.probe(audio_path)
            audio_info = next((stream for stream in probe['streams'] if stream['codec_type'] == 'audio'), None)
            
            if audio_info is None:
                raise RuntimeError("无法获取音频信息")
            
            duration = float(probe['format']['duration'])
            
            # 计算分段数量
            num_segments = max(1, int(duration / segment_length) + (1 if duration % segment_length > 0 else 0))
            
            logging.info(f"将处理 {duration:.2f}秒 音频，分为 {num_segments} 个片段")
            
            # 处理结果
            all_segments = []
            detected_language = None
            
            # Each invocation owns its directory.  The former global names
            # (``/tmp/segment_0_<basename>``) collided when two jobs processed
            # files with the same name, and a crash could leave audio behind.
            with tempfile.TemporaryDirectory(
                prefix="video-translator-segments-"
            ) as temp_dir:
                for i in range(num_segments):
                    if self.cancel_flag:
                        logging.info("处理被用户取消")
                        raise InterruptedError("语音识别已取消")

                    start_time = i * segment_length

                    # 最后一段的实际长度可能更短
                    actual_segment_length = min(segment_length, duration - start_time)

                    # A deterministic WAV container avoids relying on the
                    # source extension for FFmpeg output format selection.
                    segment_path = os.path.join(temp_dir, f"segment_{i}.wav")

                    # 分割音频
                    (
                        ffmpeg
                        .input(audio_path, ss=start_time, t=actual_segment_length)
                        .output(segment_path, acodec="pcm_s16le", ac=1, ar=16000)
                        .run(quiet=True, overwrite_output=True)
                    )

                    # 设置段落回调
                    segment_progress_callback = None
                    if progress_callback:
                        def segment_callback(p, segment_index=i):
                            # 将单个段进度转换为整体进度
                            overall_progress = int(
                                (segment_index / num_segments + p / 100 / num_segments) * 100
                            )
                            progress_callback(overall_progress)

                        segment_progress_callback = segment_callback

                    # 处理该段落
                    logging.info(f"处理片段 {i+1}/{num_segments} (开始于 {start_time:.2f}s)")
                    result = self.transcribe(
                        segment_path,
                        language=(detected_language or language),
                        progress_callback=segment_progress_callback
                    )

                    # 如果是第一段，记录检测到的语言
                    if i == 0 and not language:
                        detected_language = result.get("detected_language")
                        logging.info(f"检测到语言: {detected_language}")

                    # 调整段落时间戳
                    for segment in result["segments"]:
                        segment["start"] += start_time
                        segment["end"] += start_time

                    # 添加到结果中
                    all_segments.extend(result["segments"])
            
            # 合并结果
            return {
                "text": " ".join(s["text"] for s in all_segments),
                "segments": all_segments,
                "language": detected_language or language,
                "detected_language": detected_language
            }
            
        except Exception as e:
            logging.error(f"分段处理音频失败: {str(e)}")
            raise
    
    def transcribe_async(self, audio_path: str, callback: Callable[[Dict[str, Any]], None], 
                       error_callback: Callable[[str], None], **kwargs):
        """
        异步转写音频文件
        
        Args:
            audio_path: 音频文件路径
            callback: 完成回调函数，接收结果字典
            error_callback: 错误回调函数，接收错误信息
            **kwargs: 传递给transcribe的其他参数
        """
        def process_thread():
            try:
                result = self.transcribe(audio_path, **kwargs)
                callback(result)
            except Exception as e:
                error_callback(str(e))
        
        self.processing_thread = threading.Thread(target=process_thread)
        self.processing_thread.daemon = True
        self.processing_thread.start()
    
    def process_segments_async(self, audio_path: str, callback: Callable[[Dict[str, Any]], None],
                             error_callback: Callable[[str], None], **kwargs):
        """
        异步分段处理音频文件
        
        Args:
            audio_path: 音频文件路径
            callback: 完成回调函数，接收结果字典
            error_callback: 错误回调函数，接收错误信息
            **kwargs: 传递给process_segments的其他参数
        """
        def process_thread():
            try:
                result = self.process_segments(audio_path, **kwargs)
                callback(result)
            except Exception as e:
                error_callback(str(e))
        
        self.processing_thread = threading.Thread(target=process_thread)
        self.processing_thread.daemon = True
        self.processing_thread.start()
    
    def cancel(self):
        """取消正在进行的处理"""
        self.cancel_flag = True
        logging.info("语音识别取消请求已发出")
    
    def unload_model(self):
        """卸载模型以释放内存"""
        if self.model is not None:
            # 移除模型引用，让Python的垃圾回收器释放内存
            self.model = None
            # 尝试释放CUDA内存（如果使用GPU）
            if self.device == "cuda" and self._cuda_available():
                torch.cuda.empty_cache()
            logging.info("已卸载Whisper模型")
    
    @staticmethod
    def post_process_result(result: Dict[str, Any]) -> Dict[str, Any]:
        """
        后处理识别结果，改善标点符号和段落结构
        
        Args:
            result: 识别结果字典
            
        Returns:
            处理后的结果字典
        """
        segments = result.get("segments", [])
        
        # 这里可以实现更复杂的后处理逻辑，例如：
        # 1. 合并短段落
        # 2. 规范化标点符号
        # 3. 移除重复短语
        
        # 简单示例：确保每个句子以标点符号结束
        for i, segment in enumerate(segments):
            text = segment["text"].strip()
            if text and text[-1] not in ['.', '?', '!', '。', '？', '！']:
                # 如果是句子中间部分，添加逗号，否则添加句号
                if i < len(segments)-1 and len(text) < 50:
                    segments[i]["text"] = text + ','
                else:
                    segments[i]["text"] = text + '.'
        
        # 更新完整文本
        result["text"] = " ".join(s["text"] for s in segments)
        return result
    
    def cache_result(self, audio_path: str, result: Dict[str, Any]) -> bool:
        """
        缓存识别结果
        
        Args:
            audio_path: 音频文件路径
            result: 识别结果
            
        Returns:
            是否成功缓存
        """
        try:
            # 为缓存文件构建路径
            cache_dir = ensure_private_directory(get_transcription_cache_dir())
            
            # 使用音频文件的哈希作为缓存文件名
            audio_hash = self._file_hash(audio_path)
            cache_path = cache_dir / f"{audio_hash}_{self.model_name}.json"
            
            # Write beside the destination and atomically replace it.  A
            # serialization error, crash, or power loss must not destroy a
            # previously valid transcription cache entry.
            descriptor, temp_name = tempfile.mkstemp(
                prefix=f".{cache_path.name}.",
                suffix=".tmp",
                dir=cache_dir,
            )
            try:
                with os.fdopen(descriptor, 'w', encoding='utf-8') as f:
                    json.dump(result, f, ensure_ascii=False, indent=2)
                    f.flush()
                    os.fsync(f.fileno())
                try:
                    os.chmod(temp_name, 0o600)
                except OSError:
                    pass
                os.replace(temp_name, cache_path)
            except Exception:
                try:
                    os.close(descriptor)
                except OSError:
                    pass
                try:
                    os.unlink(temp_name)
                except OSError:
                    pass
                raise
            
            logging.info(f"识别结果已缓存: {cache_path}")
            return True
            
        except Exception as e:
            logging.error(f"缓存识别结果失败: {str(e)}")
            return False
    
    def get_cached_result(self, audio_path: str) -> Optional[Dict[str, Any]]:
        """
        获取缓存的识别结果
        
        Args:
            audio_path: 音频文件路径
            
        Returns:
            缓存的识别结果，如果没有缓存则返回None
        """
        try:
            # 构建缓存文件路径
            cache_dir = get_transcription_cache_dir()
            audio_hash = self._file_hash(audio_path)
            cache_path = cache_dir / f"{audio_hash}_{self.model_name}.json"
            
            # 检查缓存是否存在
            if not cache_path.exists():
                return None
                
            # 读取缓存
            with cache_path.open('r', encoding='utf-8') as f:
                result = json.load(f)
            
            logging.info(f"使用缓存的识别结果: {cache_path}")
            return result
            
        except Exception as e:
            logging.error(f"读取缓存结果失败: {str(e)}")
            return None
    
    @staticmethod
    def _file_hash(file_path: str, sample_size: int = 1024*1024) -> str:
        """
        计算文件的哈希值
        
        Args:
            file_path: 文件路径
            sample_size: 用于计算哈希的文件前多少字节
            
        Returns:
            文件哈希字符串
        """
        import hashlib
        
        file_size = os.path.getsize(file_path)
        
        # 对于大文件，只使用文件大小和前sample_size字节计算哈希
        hasher = hashlib.md5()
        hasher.update(str(file_size).encode('utf-8'))
        hasher.update(os.path.basename(file_path).encode('utf-8'))
        
        with open(file_path, 'rb') as f:
            buffer = f.read(min(sample_size, file_size))
            hasher.update(buffer)
        
        return hasher.hexdigest()
