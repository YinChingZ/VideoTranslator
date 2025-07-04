import os
import uuid
import logging
import tempfile
import subprocess
import shutil
from typing import Dict, List, Tuple, Optional, Union, Any
from pathlib import Path

import ffmpeg

class VideoProcessor:
    """视频处理类，负责视频文件操作"""
    
    def __init__(self, temp_dir: Optional[str] = None):
        """
        初始化视频处理器
        Args:
            temp_dir: 临时文件目录，如未提供则使用系统临时目录
        """
        self.temp_dir = temp_dir or tempfile.gettempdir()
        os.makedirs(self.temp_dir, exist_ok=True)
    
    def get_video_info(self, video_path: str) -> Dict[str, Any]:
        """
        提取视频文件的元数据信息
        
        Args:
            video_path: 视频文件路径
            
        Returns:
            包含视频元数据的字典
        """
        try:
            probe = ffmpeg.probe(video_path)
            video_info = next((stream for stream in probe['streams'] 
                              if stream['codec_type'] == 'video'), None)
            audio_info = next((stream for stream in probe['streams']
                              if stream['codec_type'] == 'audio'), None)
            
            format_info = probe['format']
            
            result = {
                'filename': os.path.basename(video_path),
                'format': format_info.get('format_name', 'unknown'),
                'duration': float(format_info.get('duration', 0)),
                'size': int(format_info.get('size', 0)),
                'bit_rate': int(format_info.get('bit_rate', 0)) if 'bit_rate' in format_info else None,
                'has_video': video_info is not None,
                'has_audio': audio_info is not None,
            }
            
            if video_info:
                result.update({
                    'video_codec': video_info.get('codec_name', 'unknown'),
                    'width': int(video_info.get('width', 0)),
                    'height': int(video_info.get('height', 0)),
                    'fps': self._parse_frame_rate(video_info.get('avg_frame_rate', '0/1')),
                })
            
            if audio_info:
                result.update({
                    'audio_codec': audio_info.get('codec_name', 'unknown'),
                    'audio_channels': int(audio_info.get('channels', 0)),
                    'audio_sample_rate': int(audio_info.get('sample_rate', 0)),
                })
            
            return result
        except Exception as e:
            logging.error(f"获取视频信息失败: {str(e)}")
            return {'error': str(e)}
    
    def _parse_frame_rate(self, frame_rate_str: str) -> float:
        """解析帧率字符串（如 '24/1'）为浮点数"""
        if '/' in frame_rate_str:
            num, den = frame_rate_str.split('/')
            if int(den) != 0:
                return round(int(num) / int(den), 3)
        return 0.0
    
    def generate_thumbnail(self, video_path: str, time_pos: Optional[float] = None, 
                         width: int = 320) -> Optional[str]:
        """
        从视频生成缩略图
        
        Args:
            video_path: 视频文件路径
            time_pos: 截取缩略图的时间位置（秒）。如未提供则使用视频中点
            width: 缩略图的宽度（保持纵横比）
            
        Returns:
            缩略图文件路径，失败则返回None
        """
        try:
            if time_pos is None:
                # 获取视频时长，选择中点位置
                video_info = self.get_video_info(video_path)
                time_pos = video_info.get('duration', 0) / 2
            
            # 确保有效的时间位置
            time_pos = max(0.0, time_pos)
            
            thumbnail_path = os.path.join(
                self.temp_dir, 
                f"thumb_{uuid.uuid4().hex}.jpg"
            )
            
            # 使用ffmpeg生成缩略图
            (
                ffmpeg.input(video_path, ss=time_pos)
                .filter('scale', width, -1)  # 保持纵横比
                .output(thumbnail_path, vframes=1)
                .overwrite_output()
                .run(capture_stdout=True, capture_stderr=True, quiet=True)
            )
            
            if os.path.exists(thumbnail_path):
                return thumbnail_path
                
        except Exception as e:
            logging.error(f"生成缩略图失败: {str(e)}")
            
        return None
    
    def extract_audio(self, video_path: str, output_path: Optional[str] = None, 
                    format: str = 'wav', sample_rate: int = 16000) -> Optional[str]:
        """
        从视频中提取音频
        
        Args:
            video_path: 视频文件路径
            output_path: 音频输出路径，如未提供则生成临时文件
            format: 音频格式，默认为wav（适合语音识别）
            sample_rate: 采样率，默认16kHz（适合语音识别）
            
        Returns:
            音频文件路径，失败则返回None
        """
        try:
            if output_path is None:
                output_path = os.path.join(
                    self.temp_dir, 
                    f"audio_{uuid.uuid4().hex}.{format}"
                )
            
            # 使用ffmpeg提取并处理音频
            (
                ffmpeg.input(video_path)
                .audio
                .filter('aresample', sample_rate)
                .output(output_path, format=format, acodec='pcm_s16le', ac=1)
                .overwrite_output()
                .run(quiet=True)
            )
            
            if os.path.exists(output_path):
                return output_path
                
        except Exception as e:
            logging.error(f"提取音频失败: {str(e)}")
            
        return None
    
    def extract_frames(self, video_path: str, output_dir: Optional[str] = None, 
                     fps: float = 1.0) -> Optional[str]:
        """
        从视频中提取帧序列
        
        Args:
            video_path: 视频文件路径
            output_dir: 帧输出目录，如未提供则创建临时目录
            fps: 提取的帧率，默认为1帧/秒
            
        Returns:
            帧序列目录路径，失败则返回None
        """
        try:
            if output_dir is None:
                output_dir = os.path.join(
                    self.temp_dir, 
                    f"frames_{uuid.uuid4().hex}"
                )
                os.makedirs(output_dir, exist_ok=True)
            
            # 构建输出路径模板
            output_pattern = os.path.join(output_dir, 'frame_%04d.jpg')
            
            # 使用ffmpeg提取帧
            (
                ffmpeg.input(video_path)
                .filter('fps', fps=fps)
                .output(output_pattern, start_number=0)
                .overwrite_output()
                .run(quiet=True)
            )
            
            # 验证是否成功提取了帧
            if os.path.exists(os.path.join(output_dir, 'frame_0000.jpg')):
                return output_dir
                
        except Exception as e:
            logging.error(f"提取视频帧失败: {str(e)}")
            
        return None
    
    def add_subtitles_to_video(self, video_path: str, subtitle_path: str, 
                             output_path: str, font: str = 'Arial', 
                             font_size: int = 24, font_color: str = 'white',
                             position: str = 'bottom') -> bool:
        """
        将字幕添加到视频
        
        Args:
            video_path: 视频文件路径
            subtitle_path: 字幕文件路径
            output_path: 输出视频路径
            font: 字体名称
            font_size: 字体大小
            font_color: 字体颜色
            position: 字幕位置（'top', 'bottom'）
            
        Returns:
            成功则返回True，失败则返回False
        """
        try:
            # 确定字幕垂直位置
            vertical_position = "10" if position == 'top' else "(h-text_h-10)"
            
            # 构建ffmpeg命令
            input_video = ffmpeg.input(video_path)
            video_stream = input_video.video
            audio_stream = input_video.audio
            
            # 使用字幕滤镜
            if subtitle_path.lower().endswith('.srt'):
                video_with_subs = video_stream.filter('subtitles', subtitle_path, 
                                   force_style=f'FontName={font},FontSize={font_size},'
                                             f'PrimaryColour=&H{font_color},OutlineColour=&H000000,'
                                             f'MarginV={20 if position == "bottom" else 10}')
            else:  # 对于其他格式，可能需要调整方法
                logging.warning(f"不支持的字幕格式: {os.path.splitext(subtitle_path)[1]}")
                return False
            
            # 合并视频和音频流到输出文件
            (
                ffmpeg.output(video_with_subs, audio_stream, output_path,
                            vcodec='libx264', preset='medium', 
                            acodec='aac', strict='experimental')
                .overwrite_output()
                .run(quiet=True)
            )
            
            return os.path.exists(output_path)
                
        except Exception as e:
            logging.error(f"向视频添加字幕失败: {str(e)}")
            return False
    
    def embed_subtitles_to_video(self, video_path: str, subtitle_path: str, 
                                output_path: str, subtitle_lang: str = 'zh') -> bool:
        """
        将字幕嵌入到视频文件中（作为字幕轨道，而不是烧入）
        
        Args:
            video_path: 视频文件路径
            subtitle_path: 字幕文件路径
            output_path: 输出视频路径
            subtitle_lang: 字幕语言代码
            
        Returns:
            成功则返回True，失败则返回False
        """
        try:
            # 检查输入文件是否存在
            if not os.path.exists(video_path):
                logging.error(f"视频文件不存在: {video_path}")
                return False
                
            if not os.path.exists(subtitle_path):
                logging.error(f"字幕文件不存在: {subtitle_path}")
                return False
            
            # 使用直接的 ffmpeg 命令行方式嵌入字幕
            try:
                cmd = [
                    'ffmpeg', '-i', video_path, '-i', subtitle_path,
                    '-c:v', 'copy', '-c:a', 'copy', '-c:s', 'mov_text',
                    '-metadata:s:s:0', f'language={subtitle_lang}',
                    '-y', output_path
                ]
                
                logging.info(f"嵌入字幕命令: {' '.join(cmd)}")
                
                result = subprocess.run(cmd, capture_output=True, text=True)
                
                if result.returncode == 0:
                    if os.path.exists(output_path):
                        logging.info(f"字幕成功嵌入到视频: {output_path}")
                        return True
                    else:
                        logging.error("嵌入字幕后输出文件未创建")
                        return False
                else:
                    logging.error(f"嵌入字幕命令失败，返回码: {result.returncode}")
                    logging.error(f"错误输出: {result.stderr}")
                    return False
                    
            except Exception as e:
                logging.error(f"嵌入字幕命令执行失败: {str(e)}")
                return False
                
        except Exception as e:
            logging.error(f"嵌入字幕到视频失败: {str(e)}")
            return False

    def burn_subtitles_to_video(self, video_path: str, subtitle_path: str,
                               output_path: str, font_size: int = 24, 
                               font_color: str = 'white', position: str = 'bottom') -> bool:
        """
        将字幕烧入到视频中（硬字幕）
        
        Args:
            video_path: 视频文件路径
            subtitle_path: 字幕文件路径
            output_path: 输出视频路径
            font_size: 字体大小
            font_color: 字体颜色
            position: 字幕位置
            
        Returns:
            成功则返回True，失败则返回False
        """
        try:
            # 检查输入文件是否存在
            if not os.path.exists(video_path):
                logging.error(f"视频文件不存在: {video_path}")
                return False
                
            if not os.path.exists(subtitle_path):
                logging.error(f"字幕文件不存在: {subtitle_path}")
                return False
            
            logging.info(f"开始烧入字幕: {subtitle_path} -> {video_path}")
            
            # 使用 ffmpeg-python 的 input() 方法来处理文件作为输入
            # 这样可以避免路径转义问题
            try:
                input_video = ffmpeg.input(video_path)
                
                if subtitle_path.lower().endswith('.ass'):
                    # 对于 ASS 文件，使用 ass 滤镜
                    output = ffmpeg.output(
                        input_video,
                        output_path,
                        vf=f'ass={subtitle_path}',
                        acodec='copy',
                        vcodec='libx264'
                    )
                else:
                    # 对于 SRT 文件，使用更直接的方法
                    # 直接通过 ffmpeg 的 input 处理字幕文件
                    subtitle_input = ffmpeg.input(subtitle_path)
                    
                    # 使用 filter_complex 来处理字幕烧入
                    video_stream = input_video['v']
                    audio_stream = input_video['a']
                    
                    # 使用 overlay 方法处理字幕
                    # 这里我们使用一个更简单的方法：直接使用 ffmpeg 命令
                    # 通过 subprocess 调用，使用正确的参数格式
                    return self._burn_subtitles_direct(video_path, subtitle_path, output_path)
                
                # 执行 ffmpeg 命令
                ffmpeg.run(output, overwrite_output=True, quiet=True)
                
                # 验证输出文件是否创建成功
                if os.path.exists(output_path):
                    logging.info(f"字幕成功烧入到视频: {output_path}")
                    return True
                else:
                    logging.error("烧入字幕后输出文件未创建")
                    return False
                    
            except Exception as e:
                logging.error(f"FFmpeg-python 方法失败: {str(e)}")
                # 使用直接调用的备用方法
                return self._burn_subtitles_direct(video_path, subtitle_path, output_path)
                
        except Exception as e:
            logging.error(f"烧入字幕到视频失败: {str(e)}")
            return False
    
    def _burn_subtitles_direct(self, video_path: str, subtitle_path: str, output_path: str) -> bool:
        """
        直接使用 ffmpeg 命令行烧入字幕
        """
        try:
            # 更改工作目录到临时目录，使用相对路径
            original_cwd = os.getcwd()
            temp_dir = tempfile.gettempdir()
            
            try:
                # 创建简单文件名的临时文件
                temp_subtitle = os.path.join(temp_dir, "temp_sub.srt")
                
                # 复制字幕文件到临时位置
                shutil.copy2(subtitle_path, temp_subtitle)
                
                # 切换到临时目录
                os.chdir(temp_dir)
                
                # 使用相对路径
                cmd = [
                    'ffmpeg', '-i', video_path,
                    '-vf', 'subtitles=temp_sub.srt',
                    '-c:a', 'copy', '-c:v', 'libx264',
                    '-y', output_path
                ]
                
                logging.info(f"执行命令: {' '.join(cmd)}")
                
                # 执行命令
                result = subprocess.run(cmd, capture_output=True, text=True)
                
                if result.returncode == 0:
                    if os.path.exists(output_path):
                        logging.info(f"字幕成功烧入到视频: {output_path}")
                        return True
                    else:
                        logging.error("命令执行成功但输出文件未创建")
                        return False
                else:
                    logging.error(f"FFmpeg 命令失败，返回码: {result.returncode}")
                    logging.error(f"错误输出: {result.stderr}")
                    return False
                    
            finally:
                # 恢复原始工作目录
                os.chdir(original_cwd)
                
                # 清理临时字幕文件
                try:
                    temp_subtitle = os.path.join(temp_dir, "temp_sub.srt")
                    if os.path.exists(temp_subtitle):
                        os.unlink(temp_subtitle)
                except:
                    pass
                    
        except Exception as e:
            logging.error(f"直接命令方法失败: {str(e)}")
            return False
    
    def _burn_subtitles_fallback(self, video_path: str, subtitle_path: str, 
                                output_path: str, font_size: int = 24, 
                                font_color: str = 'white') -> bool:
        """
        字幕烧入的备用方法
        """
        try:
            # 使用最简单的 ffmpeg-python 方法
            input_stream = ffmpeg.input(video_path)
            
            # 简化的字幕烧入，不使用复杂的样式
            output_stream = ffmpeg.output(
                input_stream,
                output_path,
                vf=f'subtitles={subtitle_path}',
                acodec='copy',
                vcodec='libx264'
            )
            
            # 执行命令，不使用 quiet 模式以便调试
            ffmpeg.run(output_stream, overwrite_output=True)
            
            return os.path.exists(output_path)
            
        except Exception as e:
            logging.error(f"备用方法也失败: {str(e)}")
            return False

    @staticmethod
    def check_ffmpeg_available() -> bool:
        """
        检查系统是否安装了FFmpeg
        
        Returns:
            可用返回True，否则返回False
        """
        try:
            result = subprocess.run(['ffmpeg', '-version'], 
                                  stdout=subprocess.PIPE, 
                                  stderr=subprocess.PIPE)
            return result.returncode == 0
        except Exception:
            return False
