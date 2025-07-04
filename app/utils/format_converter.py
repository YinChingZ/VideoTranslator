import re
import logging
from typing import Dict, List, Tuple, Optional, Union
import datetime

class FormatConverter:
    """各种格式转换功能的实现"""
    
    @staticmethod
    def srt_to_vtt(srt_content: str) -> str:
        """将SRT格式字幕转换为WebVTT格式
        
        Args:
            srt_content: SRT格式的字幕内容
            
        Returns:
            WebVTT格式的字幕内容
        """
        # 添加WebVTT头
        vtt = "WEBVTT\n\n"
        
        # 转换时间戳格式 (00:00:00,000 -> 00:00:00.000)
        lines = srt_content.splitlines()
        i = 0
        
        while i < len(lines):
            line = lines[i].strip()
            i += 1
            
            # 跳过空行
            if not line:
                vtt += "\n"
                continue
            
            # 检查是否是序号行（纯数字）
            if line.isdigit():
                # 读取时间戳行
                if i < len(lines):
                    timestamp_line = lines[i].strip()
                    i += 1
                    
                    # 转换时间戳格式
                    timestamp_line = timestamp_line.replace(',', '.')
                    vtt += timestamp_line + "\n"
                    
                    # 复制字幕文本直到下一个空行或文件结束
                    while i < len(lines) and lines[i].strip():
                        vtt += lines[i] + "\n"
                        i += 1
            else:
                # 不是序号行，直接复制
                vtt += line + "\n"
        
        return vtt
    
    @staticmethod
    def vtt_to_srt(vtt_content: str) -> str:
        """将WebVTT格式字幕转换为SRT格式
        
        Args:
            vtt_content: WebVTT格式的字幕内容
            
        Returns:
            SRT格式的字幕内容
        """
        # 跳过WebVTT头
        if vtt_content.strip().startswith("WEBVTT"):
            lines = vtt_content.splitlines()
            start_idx = 0
            for idx, line in enumerate(lines):
                if line.strip() == "WEBVTT":
                    start_idx = idx + 1
                    break
            
            lines = lines[start_idx:]
            vtt_content = "\n".join(lines)
        
        # 转换时间戳格式 (00:00:00.000 -> 00:00:00,000)
        srt_content = vtt_content.replace('.', ',')
        
        # 添加序号
        lines = srt_content.splitlines()
        srt = ""
        counter = 1
        i = 0
        
        while i < len(lines):
            line = lines[i].strip()
            i += 1
            
            # 跳过空行
            if not line:
                srt += "\n"
                continue
            
            # 检查是否是时间戳行
            if re.match(r'\d{2}:\d{2}:\d{2},\d{3} --> \d{2}:\d{2}:\d{2},\d{3}', line):
                # 添加序号
                srt += str(counter) + "\n"
                counter += 1
                
                # 添加时间戳
                srt += line + "\n"
                
                # 复制字幕文本直到下一个空行或文件结束
                while i < len(lines) and lines[i].strip():
                    srt += lines[i] + "\n"
                    i += 1
                
                srt += "\n"
            else:
                # 不是时间戳行，直接复制
                srt += line + "\n"
        
        return srt
    
    @staticmethod
    def milliseconds_to_timestamp(ms: int) -> str:
        """将毫秒转换为时间戳格式 (00:00:00,000)
        
        Args:
            ms: 毫秒
            
        Returns:
            格式化的时间戳
        """
        seconds, milliseconds = divmod(ms, 1000)
        minutes, seconds = divmod(seconds, 60)
        hours, minutes = divmod(minutes, 60)
        
        return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"
    
    @staticmethod
    def timestamp_to_milliseconds(timestamp: str) -> int:
        """将时间戳格式 (00:00:00,000 或 00:00:00.000) 转换为毫秒
        
        Args:
            timestamp: 时间戳字符串
            
        Returns:
            对应的毫秒数
        """
        # 统一格式，将.替换为,
        timestamp = timestamp.replace('.', ',')
        
        # 解析时间戳
        pattern = r'(\d{2}):(\d{2}):(\d{2}),(\d{3})'
        match = re.match(pattern, timestamp)
        
        if match:
            hours = int(match.group(1))
            minutes = int(match.group(2))
            seconds = int(match.group(3))
            milliseconds = int(match.group(4))
            
            total_ms = (hours * 3600 + minutes * 60 + seconds) * 1000 + milliseconds
            return total_ms
        
        raise ValueError(f"无效的时间戳格式: {timestamp}")
    
    @staticmethod
    def seconds_to_timestamp(seconds: float) -> str:
        """将秒转换为时间戳格式
        
        Args:
            seconds: 秒数（可以是浮点数）
            
        Returns:
            格式化的时间戳
        """
        ms = int(seconds * 1000)
        return FormatConverter.milliseconds_to_timestamp(ms)
    
    @staticmethod
    def timestamp_to_seconds(timestamp: str) -> float:
        """将时间戳转换为秒
        
        Args:
            timestamp: 时间戳字符串
            
        Returns:
            秒数（浮点数）
        """
        ms = FormatConverter.timestamp_to_milliseconds(timestamp)
        return ms / 1000.0
    
    @staticmethod
    def detect_encoding(file_path: str) -> str:
        """检测文件编码
        
        Args:
            file_path: 文件路径
            
        Returns:
            检测到的编码
        """
        import chardet
        
        # 读取文件的前4KB以检测编码
        with open(file_path, 'rb') as f:
            raw_data = f.read(4096)
            result = chardet.detect(raw_data)
        
        encoding = result['encoding']
        confidence = result['confidence']
        
        if confidence < 0.7:
            logging.warning(f"编码检测置信度低: {file_path} -> {encoding} ({confidence:.2f})")
            # 默认回退到UTF-8
            return 'utf-8'
        
        return encoding
    
    @staticmethod
    def convert_encoding(content: str, from_encoding: str, to_encoding: str = 'utf-8') -> str:
        """转换文本编码
        
        Args:
            content: 要转换的文本内容
            from_encoding: 源编码
            to_encoding: 目标编码
            
        Returns:
            转换后的文本
        """
        try:
            # 如果已经是Unicode字符串，则先转换为字节
            if isinstance(content, str):
                content_bytes = content.encode(from_encoding)
            else:
                content_bytes = content
                
            # 转换为目标编码的字符串
            return content_bytes.decode(to_encoding)
        except Exception as e:
            logging.error(f"编码转换失败: {from_encoding} -> {to_encoding}: {str(e)}")
            return content  # 返回原始内容
    
    @staticmethod
    def convert_language_code(code: str, from_standard: str = 'iso639-1', 
                             to_standard: str = 'iso639-2') -> str:
        """转换语言代码标准
        
        Args:
            code: 语言代码
            from_standard: 源标准 ('iso639-1', 'iso639-2', 'custom')
            to_standard: 目标标准 ('iso639-1', 'iso639-2', 'custom')
            
        Returns:
            转换后的语言代码
        """
        # 常见语言代码映射
        iso639_1_to_2 = {
            'zh': 'zho', 'en': 'eng', 'fr': 'fra', 'de': 'deu',
            'ja': 'jpn', 'ko': 'kor', 'ru': 'rus', 'es': 'spa',
            'it': 'ita', 'pt': 'por', 'ar': 'ara', 'hi': 'hin',
            'tr': 'tur', 'vi': 'vie', 'th': 'tha', 'id': 'ind'
        }
        
        iso639_2_to_1 = {v: k for k, v in iso639_1_to_2.items()}
        
        # 自定义映射 (例如 OpenAI Whisper 使用的格式)
        custom_to_iso639_1 = {
            'zh-cn': 'zh', 'zh-tw': 'zh', 'en-us': 'en', 'en-gb': 'en',
            'simplified chinese': 'zh', 'traditional chinese': 'zh',
            'english': 'en', 'french': 'fr', 'german': 'de',
            'japanese': 'ja', 'korean': 'ko', 'russian': 'ru',
            'spanish': 'es', 'italian': 'it', 'portuguese': 'pt'
        }
        
        # 转换为小写以提高匹配率
        code = code.lower()
        
        # 标准化地区代码，如zh-CN -> zh
        if from_standard == 'custom':
            if code in custom_to_iso639_1:
                code = custom_to_iso639_1[code]
            elif '-' in code:
                code = code.split('-')[0]
        
        # 进行转换
        if from_standard == 'iso639-1' and to_standard == 'iso639-2':
            return iso639_1_to_2.get(code, code)
        elif from_standard == 'iso639-2' and to_standard == 'iso639-1':
            return iso639_2_to_1.get(code, code)
        elif from_standard == 'custom' and to_standard == 'iso639-1':
            return custom_to_iso639_1.get(code, code)
        elif from_standard == 'custom' and to_standard == 'iso639-2':
            iso639_1_code = custom_to_iso639_1.get(code, code)
            return iso639_1_to_2.get(iso639_1_code, iso639_1_code)
        else:
            # 相同标准或不支持的转换，返回原代码
            return code
    
    @staticmethod
    def rgb_to_hex(r: int, g: int, b: int) -> str:
        """将RGB颜色值转换为十六进制颜色代码
        
        Args:
            r: 红色分量 (0-255)
            g: 绿色分量 (0-255)
            b: 蓝色分量 (0-255)
            
        Returns:
            十六进制颜色代码 (#RRGGBB)
        """
        return f"#{r:02x}{g:02x}{b:02x}"
    
    @staticmethod
    def hex_to_rgb(hex_color: str) -> Tuple[int, int, int]:
        """将十六进制颜色代码转换为RGB颜色值
        
        Args:
            hex_color: 十六进制颜色代码 (#RRGGBB 或 RRGGBB)
            
        Returns:
            包含RGB分量的元组 (R, G, B)
        """
        # 移除井号（如果存在）
        hex_color = hex_color.lstrip('#')
        
        # 将十六进制转换为RGB
        r = int(hex_color[0:2], 16)
        g = int(hex_color[2:4], 16)
        b = int(hex_color[4:6], 16)
        
        return (r, g, b)
    
    @staticmethod
    def format_time_code(seconds: float, frame_rate: float = 30.0, 
                        format_type: str = 'srt') -> str:
        """将秒转换为各种时间代码格式
        
        Args:
            seconds: 秒数
            frame_rate: 帧率（用于计算帧部分）
            format_type: 格式类型 ('srt', 'vtt', 'fcpxml', 'frames', 'timecode')
            
        Returns:
            格式化的时间代码
        """
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        msecs = int((seconds % 1) * 1000)
        frames = int((seconds % 1) * frame_rate)
        
        if format_type == 'srt':
            return f"{hours:02d}:{minutes:02d}:{secs:02d},{msecs:03d}"
        elif format_type == 'vtt':
            return f"{hours:02d}:{minutes:02d}:{secs:02d}.{msecs:03d}"
        elif format_type == 'fcpxml':
            return f"{hours}h{minutes}m{secs}s{frames}f"
        elif format_type == 'frames':
            total_frames = int(seconds * frame_rate)
            return str(total_frames)
        elif format_type == 'timecode':
            return f"{hours:02d}:{minutes:02d}:{secs:02d}:{frames:02d}"
        else:
            raise ValueError(f"不支持的时间代码格式: {format_type}")

def format_time(seconds: float, include_ms: bool = True) -> str:
    """
    将秒数转换为格式化的时间字符串
    
    Args:
        seconds: 秒数(可以是浮点数)
        include_ms: 是否包含毫秒
        
    Returns:
        格式化的时间字符串
    """
    if include_ms:
        return FormatConverter.seconds_to_timestamp(seconds)
    else:
        # 不包含毫秒的格式
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"

def parse_time(time_str: str) -> float:
    """
    将格式化的时间字符串解析为秒数
    
    Args:
        time_str: 格式化的时间字符串
        
    Returns:
        时间对应的秒数(浮点数)
    """
    try:
        return FormatConverter.timestamp_to_seconds(time_str)
    except ValueError:
        # 处理可能的替代格式
        if '.' in time_str or ',' in time_str:
            # 已经是标准格式，尝试直接解析
            return FormatConverter.timestamp_to_seconds(time_str)
        else:
            # 假设格式为 HH:MM:SS
            parts = time_str.split(':')
            if len(parts) == 3:
                hours = int(parts[0])
                minutes = int(parts[1])
                seconds = int(parts[2])
                return hours * 3600 + minutes * 60 + seconds
            elif len(parts) == 2:
                minutes = int(parts[0])
                seconds = int(parts[1])
                return minutes * 60 + seconds
            else:
                return float(time_str)
