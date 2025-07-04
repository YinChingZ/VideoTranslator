#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Subtitle processing module for video translation system.
Handles subtitle file operations, format conversions, timing adjustments,
and embedding subtitles into videos.
"""

import os
import re
import logging
import codecs
import tempfile
import subprocess
from typing import List, Dict, Tuple, Optional, Union, Any
from dataclasses import dataclass
from datetime import timedelta

# Third-party imports
import pysrt
import webvtt
from chardet import detect

logger = logging.getLogger(__name__)

@dataclass
class SubtitleSegment:
    """Data class representing a subtitle segment with timing and text."""
    start_time: float  # Start time in seconds
    end_time: float    # End time in seconds
    original_text: str  # Original language text
    translated_text: str  # Translated text
    index: int = 0     # Subtitle index/number
    style: Dict[str, Any] = None  # Style properties (font, color, position)

    def __post_init__(self):
        if self.style is None:
            self.style = {}


class SubtitleProcessor:
    """
    Main class for handling subtitle operations including parsing, 
    formatting, conversion, and timing adjustments.
    """
    
    # Supported subtitle formats and their file extensions
    SUPPORTED_FORMATS = {
        'srt': '.srt',
        'vtt': '.vtt',
        'ass': '.ass',
        'ssa': '.ssa',
        'sub': '.sub',
        'sbv': '.sbv'
    }
    
    def __init__(self, ffmpeg_path: str = 'ffmpeg'):
        """
        Initialize the SubtitleProcessor.
        
        Args:
            ffmpeg_path: Path to ffmpeg executable for video operations
        """
        self.ffmpeg_path = ffmpeg_path
        self.segments: List[SubtitleSegment] = []
        self._validate_dependencies()
    
    def _validate_dependencies(self) -> None:
        """Validate external dependencies are available."""
        try:
            subprocess.run([self.ffmpeg_path, "-version"], 
                          stdout=subprocess.PIPE, 
                          stderr=subprocess.PIPE)
        except (subprocess.SubprocessError, FileNotFoundError):
            logger.warning("FFmpeg not found at specified path. "
                          "Subtitle embedding may not work correctly.")
    
    def load_from_file(self, file_path: str) -> List[SubtitleSegment]:
        """
        Load subtitles from a file based on file extension.
        
        Args:
            file_path: Path to the subtitle file
            
        Returns:
            List of SubtitleSegment objects
            
        Raises:
            ValueError: If file format is not supported or file is invalid
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Subtitle file not found: {file_path}")
            
        file_ext = os.path.splitext(file_path)[1].lower()
        
        try:
            if file_ext == '.srt':
                return self._load_srt(file_path)
            elif file_ext == '.vtt':
                return self._load_vtt(file_path)
            elif file_ext in ['.ass', '.ssa']:
                return self._load_ass(file_path)
            elif file_ext == '.sub':
                return self._load_sub(file_path)
            else:
                raise ValueError(f"Unsupported subtitle format: {file_ext}")
        except Exception as e:
            logger.error(f"Error loading subtitle file: {e}")
            raise ValueError(f"Failed to parse subtitle file: {e}")
    
    def _detect_encoding(self, file_path: str) -> str:
        """
        Detect the encoding of a file.
        
        Args:
            file_path: Path to the file
            
        Returns:
            Detected encoding
        """
        with open(file_path, 'rb') as f:
            raw_data = f.read(10000)  # Read first 10000 bytes for detection
            result = detect(raw_data)
            encoding = result['encoding'] if result['confidence'] > 0.7 else 'utf-8'
            return encoding
    
    def _load_srt(self, file_path: str) -> List[SubtitleSegment]:
        """
        Load subtitles from an SRT file.
        
        Args:
            file_path: Path to the SRT file
            
        Returns:
            List of SubtitleSegment objects
        """
        encoding = self._detect_encoding(file_path)
        subs = pysrt.open(file_path, encoding=encoding)
        
        segments = []
        for index, sub in enumerate(subs):
            start_time = self._time_to_seconds(sub.start.hours, sub.start.minutes, 
                                             sub.start.seconds, sub.start.milliseconds)
            end_time = self._time_to_seconds(sub.end.hours, sub.end.minutes, 
                                           sub.end.seconds, sub.end.milliseconds)
            
            # Initial loading assumes original text only
            segments.append(SubtitleSegment(
                start_time=start_time,
                end_time=end_time,
                original_text=sub.text,
                translated_text="",
                index=sub.index
            ))
        
        self.segments = segments
        return segments
    
    def _load_vtt(self, file_path: str) -> List[SubtitleSegment]:
        """
        Load subtitles from a WebVTT file.
        
        Args:
            file_path: Path to the VTT file
            
        Returns:
            List of SubtitleSegment objects
        """
        vtt = webvtt.read(file_path)
        
        segments = []
        for i, caption in enumerate(vtt):
            # Parse start time (format: HH:MM:SS.mmm)
            start_parts = caption.start.split(':')
            start_sec_ms = start_parts[2].split('.')
            start_time = self._time_to_seconds(
                int(start_parts[0]), int(start_parts[1]), 
                int(start_sec_ms[0]), int(start_sec_ms[1].ljust(3, '0'))
            )
            
            # Parse end time
            end_parts = caption.end.split(':')
            end_sec_ms = end_parts[2].split('.')
            end_time = self._time_to_seconds(
                int(end_parts[0]), int(end_parts[1]), 
                int(end_sec_ms[0]), int(end_sec_ms[1].ljust(3, '0'))
            )
            
            # Clean text (remove HTML tags if present)
            text = re.sub(r'<[^>]+>', '', caption.text)
            
            segments.append(SubtitleSegment(
                start_time=start_time,
                end_time=end_time,
                original_text=text,
                translated_text="",
                index=i+1
            ))
        
        self.segments = segments
        return segments
    
    def _load_ass(self, file_path: str) -> List[SubtitleSegment]:
        """
        Load subtitles from an ASS/SSA file.
        
        Args:
            file_path: Path to the ASS/SSA file
            
        Returns:
            List of SubtitleSegment objects
        """
        encoding = self._detect_encoding(file_path)
        segments = []
        
        with codecs.open(file_path, 'r', encoding=encoding) as f:
            lines = f.readlines()
            
        dialogue_section = False
        dialogue_format = []
        index = 1
        
        for line in lines:
            line = line.strip()
            
            # Detect dialogue format line
            if line.startswith('[Events]'):
                dialogue_section = True
                continue
                
            if dialogue_section and line.startswith('Format:'):
                # Parse format line to understand dialogue structure
                format_parts = [part.strip() for part in line[7:].split(',')]
                dialogue_format = format_parts
                continue
                
            if dialogue_section and line.startswith('Dialogue:'):
                # Parse dialogue line
                parts = [part.strip() for part in line[9:].split(',', len(dialogue_format)-1)]
                dialogue_dict = dict(zip(dialogue_format, parts))
                
                if 'Start' in dialogue_dict and 'End' in dialogue_dict and 'Text' in dialogue_dict:
                    # Parse start time (format: H:MM:SS.cc)
                    start_time = self._parse_ass_time(dialogue_dict['Start'])
                    end_time = self._parse_ass_time(dialogue_dict['End'])
                    
                    # Clean ASS text formatting
                    text = re.sub(r'{\\[^}]*}', '', dialogue_dict['Text'])
                    
                    # Create segment
                    segments.append(SubtitleSegment(
                        start_time=start_time,
                        end_time=end_time,
                        original_text=text,
                        translated_text="",
                        index=index
                    ))
                    index += 1
        
        self.segments = segments
        return segments
    
    def _load_sub(self, file_path: str) -> List[SubtitleSegment]:
        """
        Load subtitles from a MicroDVD .sub file.
        
        Args:
            file_path: Path to the .sub file
            
        Returns:
            List of SubtitleSegment objects
            
        Note:
            This requires framerate information for accurate timing
            By default assumes 25 fps if not specified in the file
        """
        encoding = self._detect_encoding(file_path)
        fps = 25.0  # Default framerate
        
        segments = []
        
        with codecs.open(file_path, 'r', encoding=encoding) as f:
            lines = f.readlines()
            
        for i, line in enumerate(lines):
            line = line.strip()
            
            # Check for fps information in first line
            if i == 0 and re.match(r'^\{\d+\}\{\d+\}\d+\.\d+$', line):
                fps = float(line.split('}')[2])
                continue
                
            # Match frame pattern {start_frame}{end_frame}text
            match = re.match(r'^\{(\d+)\}\{(\d+)\}(.*?)$', line)
            if match:
                start_frame = int(match.group(1))
                end_frame = int(match.group(2))
                text = match.group(3)
                
                # Convert frames to seconds
                start_time = start_frame / fps
                end_time = end_frame / fps
                
                segments.append(SubtitleSegment(
                    start_time=start_time,
                    end_time=end_time,
                    original_text=text,
                    translated_text="",
                    index=i+1
                ))
        
        self.segments = segments
        return segments
    
    def _parse_ass_time(self, time_str: str) -> float:
        """
        Parse ASS/SSA time format (H:MM:SS.cc) to seconds.
        
        Args:
            time_str: Time string in ASS format
            
        Returns:
            Time in seconds as float
        """
        parts = time_str.split(':')
        if len(parts) != 3:
            raise ValueError(f"Invalid ASS time format: {time_str}")
            
        hours = int(parts[0])
        minutes = int(parts[1])
        
        sec_parts = parts[2].split('.')
        seconds = int(sec_parts[0])
        centiseconds = int(sec_parts[1]) if len(sec_parts) > 1 else 0
        
        # Convert to milliseconds for consistency
        milliseconds = centiseconds * 10
        
        return self._time_to_seconds(hours, minutes, seconds, milliseconds)
    
    def _time_to_seconds(self, hours: int, minutes: int, seconds: int, milliseconds: int) -> float:
        """
        Convert time components to seconds.
        
        Args:
            hours: Hours component
            minutes: Minutes component
            seconds: Seconds component
            milliseconds: Milliseconds component
            
        Returns:
            Time in seconds as float
        """
        return hours * 3600 + minutes * 60 + seconds + milliseconds / 1000
    
    def _seconds_to_time_parts(self, seconds: float) -> Tuple[int, int, int, int]:
        """
        Convert seconds to time components.
        
        Args:
            seconds: Time in seconds
            
        Returns:
            Tuple of (hours, minutes, seconds, milliseconds)
        """
        total_milliseconds = int(seconds * 1000)
        
        hours = total_milliseconds // 3600000
        total_milliseconds %= 3600000
        
        minutes = total_milliseconds // 60000
        total_milliseconds %= 60000
        
        secs = total_milliseconds // 1000
        milliseconds = total_milliseconds % 1000
        
        return hours, minutes, secs, milliseconds
    
    def create_from_segments(self, segments: List[Dict]) -> List[SubtitleSegment]:
        """
        Create subtitle segments from a list of dictionaries.
        Useful when importing from speech recognition and translation results or project files.
        """
        self.segments = []
        for i, segment in enumerate(segments):
            try:
                # 支持多种键名: 'start'或'start_time', 'end'或'end_time',
                # 'original'或'original_text'或'text', 'translation'或'translated_text'
                start_val = segment.get('start', segment.get('start_time', 0))
                end_val = segment.get('end', segment.get('end_time', 0))
                orig = segment.get('original', segment.get('original_text', segment.get('text', '')))
                trans = segment.get('translation', segment.get('translated_text', ''))
                style = segment.get('style', None)
                subtitle_seg = SubtitleSegment(
                    start_time=float(start_val),
                    end_time=float(end_val),
                    original_text=orig,
                    translated_text=trans,
                    index=i+1,
                    style=style
                )
                self.segments.append(subtitle_seg)
            except (ValueError, TypeError) as e:
                logger.warning(f"Skipping invalid segment {i}: {e}")
        return self.segments
    
    def save_to_file(self, output_path: str, format_type: str = None, 
                    include_original: bool = False) -> str:
        """
        Save subtitle segments to a file in the specified format.
        
        Args:
            output_path: Path where to save the subtitle file
            format_type: Format to save as (srt, vtt, ass), if None, infer from path
            include_original: Whether to include original text with translations
            
        Returns:
            Path to the saved file
            
        Raises:
            ValueError: If format is not supported or segments are empty
        """
        if not self.segments:
            raise ValueError("No subtitle segments to save")
        
        # If format not specified, infer from output path
        if format_type is None:
            ext = os.path.splitext(output_path)[1].lower()
            format_type = ext[1:] if ext in ['.srt', '.vtt', '.ass', '.ssa', '.sub'] else 'srt'
        
        # Make sure format is supported
        if format_type not in self.SUPPORTED_FORMATS:
            raise ValueError(f"Unsupported subtitle format: {format_type}")
            
        # Ensure the directory exists
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        
        # Call appropriate save method based on format
        if format_type == 'srt':
            self._save_srt(output_path, include_original)
        elif format_type == 'vtt':
            self._save_vtt(output_path, include_original)
        elif format_type in ['ass', 'ssa']:
            self._save_ass(output_path, include_original)
        elif format_type == 'sub':
            self._save_sub(output_path, include_original)
        
        logger.info(f"Saved subtitles to {output_path} in {format_type} format")
        return output_path
    
    def _save_srt(self, output_path: str, include_original: bool = False) -> None:
        """
        Save subtitles in SRT format.
        
        Args:
            output_path: Path where to save the SRT file
            include_original: Whether to include original text with translations
        """
        srt_content = []
        
        for i, segment in enumerate(self.segments):
            start_h, start_m, start_s, start_ms = self._seconds_to_time_parts(segment.start_time)
            end_h, end_m, end_s, end_ms = self._seconds_to_time_parts(segment.end_time)
            
            # Format: index + timestamp + text
            srt_content.append(f"{i+1}")
            
            # Format timestamp as: 00:00:00,000 --> 00:00:00,000
            timestamp = (f"{start_h:02d}:{start_m:02d}:{start_s:02d},{start_ms:03d} --> "
                        f"{end_h:02d}:{end_m:02d}:{end_s:02d},{end_ms:03d}")
            srt_content.append(timestamp)
            
            # Format text based on whether to include original
            if include_original and segment.original_text:
                text = f"{segment.original_text}\n{segment.translated_text}"
            else:
                text = segment.translated_text or segment.original_text
            
            srt_content.append(text)
            srt_content.append("")  # Empty line between entries
        
        # Write to file
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(srt_content))
    
    def _save_vtt(self, output_path: str, include_original: bool = False) -> None:
        """
        Save subtitles in WebVTT format.
        
        Args:
            output_path: Path where to save the VTT file
            include_original: Whether to include original text with translations
        """
        vtt_content = ["WEBVTT", ""]  # Header required for WebVTT
        
        for i, segment in enumerate(self.segments):
            start_h, start_m, start_s, start_ms = self._seconds_to_time_parts(segment.start_time)
            end_h, end_m, end_s, end_ms = self._seconds_to_time_parts(segment.end_time)
            
            # Optional cue identifier
            vtt_content.append(f"{i+1}")
            
            # Format timestamp: 00:00:00.000 --> 00:00:00.000
            # Note: VTT uses periods for milliseconds, not commas
            timestamp = (f"{start_h:02d}:{start_m:02d}:{start_s:02d}.{start_ms:03d} --> "
                        f"{end_h:02d}:{end_m:02d}:{end_s:02d}.{end_ms:03d}")
            vtt_content.append(timestamp)
            
            # Format text
            if include_original and segment.original_text:
                text = f"{segment.original_text}\n{segment.translated_text}"
            else:
                text = segment.translated_text or segment.original_text
                
            vtt_content.append(text)
            vtt_content.append("")  # Empty line between entries
        
        # Write to file
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(vtt_content))
    
    def _save_ass(self, output_path: str, include_original: bool = False) -> None:
        """
        Save subtitles in ASS/SSA format.
        
        Args:
            output_path: Path where to save the ASS file
            include_original: Whether to include original text with translations
        """
        # ASS file sections
        ass_header = [
            "[Script Info]",
            "Title: Translated Subtitles",
            "ScriptType: v4.00+",
            "Collisions: Normal",
            "PlayResX: 1920",
            "PlayResY: 1080",
            "Timer: 100.0000",
            "",
            "[V4+ Styles]",
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
            "Style: Default,Arial,48,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,0,0,0,0,100,100,0,0,1,2,2,2,10,10,10,1",
            "",
            "[Events]",
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"
        ]
        
        ass_events = []
        
        for segment in self.segments:
            start_h, start_m, start_s, start_ms = self._seconds_to_time_parts(segment.start_time)
            end_h, end_m, end_s, end_ms = self._seconds_to_time_parts(segment.end_time)
            
            # Convert milliseconds to centiseconds for ASS format
            start_cs = start_ms // 10
            end_cs = end_ms // 10
            
            # Format time: H:MM:SS.cs
            start_time = f"{start_h}:{start_m:02d}:{start_s:02d}.{start_cs:02d}"
            end_time = f"{end_h}:{end_m:02d}:{end_s:02d}.{end_cs:02d}"
            
            # Format text
            if include_original and segment.original_text:
                text = f"{segment.original_text}\\N{segment.translated_text}"
            else:
                text = segment.translated_text or segment.original_text
            
            # Create dialogue line
            dialogue = f"Dialogue: 0,{start_time},{end_time},Default,,0,0,0,,{text}"
            ass_events.append(dialogue)
        
        # Combine all sections
        ass_content = ass_header + ass_events
        
        # Write to file
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(ass_content))
    
    def _save_sub(self, output_path: str, include_original: bool = False) -> None:
        """
        Save subtitles in MicroDVD .sub format.
        
        Args:
            output_path: Path where to save the .sub file
            include_original: Whether to include original text with translations
        """
        fps = 25.0  # Default framerate
        sub_content = []
        
        # Add framerate information as first line
        sub_content.append(f"{{1}}{{1}}{fps}")
        
        for segment in self.segments:
            # Convert seconds to frames
            start_frame = int(segment.start_time * fps)
            end_frame = int(segment.end_time * fps)
            
            # Format text
            if include_original and segment.original_text:
                text = f"{segment.original_text}|{segment.translated_text}"
            else:
                text = segment.translated_text or segment.original_text
            
            # Create line
            line = f"{{{start_frame}}}{{{end_frame}}}{text}"
            sub_content.append(line)
        
        # Write to file
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(sub_content))
    
    def adjust_timing(self, offset_seconds: float = 0, scale_factor: float = 1.0) -> None:
        """
        Adjust timing of all subtitle segments.
        
        Args:
            offset_seconds: Seconds to add/subtract from all timestamps
            scale_factor: Factor to multiply duration (e.g. 1.05 for 5% longer)
        """
        if not self.segments:
            logger.warning("No segments to adjust timing")
            return
        
        for segment in self.segments:
            # Calculate mid-point to maintain relative position when scaling
            mid_time = (segment.start_time + segment.end_time) / 2
            half_duration = (segment.end_time - segment.start_time) / 2
            
            # Apply scaling around mid-point
            scaled_half_duration = half_duration * scale_factor
            
            # Apply adjustments
            segment.start_time = mid_time - scaled_half_duration + offset_seconds
            segment.end_time = mid_time + scaled_half_duration + offset_seconds
            
            # Ensure no negative start times
            if segment.start_time < 0:
                segment.start_time = 0
                
        logger.info(f"Adjusted timing: offset={offset_seconds}s, scale={scale_factor}")
    
    def set_translated_text(self, translations: List[str]) -> None:
        """
        Set translated text for existing segments.
        
        Args:
            translations: List of translated text strings
        """
        if len(translations) != len(self.segments):
            logger.warning(f"Translation count ({len(translations)}) doesn't match "
                          f"segment count ({len(self.segments)})")
        
        # Apply translations up to the minimum of the two lists
        for i in range(min(len(translations), len(self.segments))):
            self.segments[i].translated_text = translations[i]
    
    def add_style_to_segments(self, style_properties: Dict[str, Any], 
                             segment_indices: List[int] = None) -> None:
        """
        Apply style properties to selected segments or all segments.
        
        Args:
            style_properties: Dictionary of style properties
            segment_indices: List of segment indices to apply styles to (None means all)
        """
        if not self.segments:
            logger.warning("No segments to style")
            return
            
        # If no indices provided, apply to all segments
        indices = segment_indices if segment_indices is not None else range(len(self.segments))
        
        for idx in indices:
            if 0 <= idx < len(self.segments):
                # Create style dict if it doesn't exist
                if self.segments[idx].style is None:
                    self.segments[idx].style = {}
                # Update with new properties
                self.segments[idx].style.update(style_properties)
            else:
                logger.warning(f"Segment index {idx} out of range (0-{len(self.segments)-1})")
    
    def merge_segments(self, start_idx: int, end_idx: int) -> None:
        """
        Merge consecutive subtitle segments into one.
        
        Args:
            start_idx: Index of first segment to merge
            end_idx: Index of last segment to merge (inclusive)
        """
        if (not self.segments or start_idx < 0 or end_idx >= len(self.segments) 
                or start_idx > end_idx):
            logger.error("Invalid segment indices for merging")
            return
        
        # Get segments to merge
        segments_to_merge = self.segments[start_idx:end_idx+1]
        
        # Create new merged segment
        merged_segment = SubtitleSegment(
            start_time=segments_to_merge[0].start_time,
            end_time=segments_to_merge[-1].end_time,
            original_text="\n".join(s.original_text for s in segments_to_merge if s.original_text),
            translated_text="\n".join(s.translated_text for s in segments_to_merge if s.translated_text),
            index=segments_to_merge[0].index,
            style=segments_to_merge[0].style.copy() if segments_to_merge[0].style else None
        )
        
        # Replace original segments with merged segment
        self.segments = (
            self.segments[:start_idx] + 
            [merged_segment] + 
            self.segments[end_idx+1:]
        )
        
        # Update indices of following segments
        for i in range(start_idx + 1, len(self.segments)):
            self.segments[i].index = i + 1
            
        logger.info(f"Merged segments {start_idx} to {end_idx} into one segment")
    
    def split_segment(self, segment_idx: int, split_time: float = None) -> None:
        """
        Split a subtitle segment into two at the specified time.
        
        Args:
            segment_idx: Index of segment to split
            split_time: Time at which to split (if None, splits in middle)
        """
        if not self.segments or segment_idx < 0 or segment_idx >= len(self.segments):
            logger.error("Invalid segment index for splitting")
            return
        
        segment = self.segments[segment_idx]
        
        # If no split time specified, use middle of segment
        if split_time is None:
            split_time = (segment.start_time + segment.end_time) / 2
        
        # Validate split time is within segment
        if split_time <= segment.start_time or split_time >= segment.end_time:
            logger.error("Split time must be within segment time range")
            return
        
        # Create two new segments
        segment1 = SubtitleSegment(
            start_time=segment.start_time,
            end_time=split_time,
            original_text=segment.original_text,
            translated_text=segment.translated_text,
            index=segment.index,
            style=segment.style.copy() if segment.style else None
        )
        
        segment2 = SubtitleSegment(
            start_time=split_time,
            end_time=segment.end_time,
            original_text=segment.original_text,
            translated_text=segment.translated_text,
            index=segment.index + 1,
            style=segment.style.copy() if segment.style else None
        )
        
        # Replace original segment with two new segments
        self.segments = (
            self.segments[:segment_idx] + 
            [segment1, segment2] + 
            self.segments[segment_idx+1:]
        )
        
        # Update indices of following segments
        for i in range(segment_idx + 2, len(self.segments)):
            self.segments[i].index = i + 1
            
        logger.info(f"Split segment {segment_idx} at {split_time:.3f}s")
    
    def validate_subtitles(self) -> List[Dict[str, Any]]:
        """
        Validate subtitles for common issues.
        
        Returns:
            List of dictionaries with validation issues
        """
        issues = []
        
        if not self.segments:
            issues.append({
                'type': 'error',
                'message': 'No subtitle segments found',
                'segment_idx': None
            })
            return issues
        
        prev_end = -1
        
        for i, segment in enumerate(self.segments):
            # Check for invalid timing
            if segment.start_time < 0:
                issues.append({
                    'type': 'error',
                    'message': f'Negative start time: {segment.start_time:.3f}s',
                    'segment_idx': i
                })
            
            if segment.end_time <= segment.start_time:
                issues.append({
                    'type': 'error',
                    'message': f'End time ({segment.end_time:.3f}s) <= start time ({segment.start_time:.3f}s)',
                    'segment_idx': i
                })
            
            # Check for overlapping segments
            if segment.start_time < prev_end:
                issues.append({
                    'type': 'warning',
                    'message': f'Overlaps with previous segment (starts at {segment.start_time:.3f}s, previous ends at {prev_end:.3f}s)',
                    'segment_idx': i
                })
            
            # Check for very short segments
            if segment.end_time - segment.start_time < 0.5:
                issues.append({
                    'type': 'warning',
                    'message': f'Very short duration: {(segment.end_time - segment.start_time):.3f}s',
                    'segment_idx': i
                })
            
            # Check for very long segments
            if segment.end_time - segment.start_time > 7:
                issues.append({
                    'type': 'warning',
                    'message': f'Very long duration: {(segment.end_time - segment.start_time):.3f}s',
                    'segment_idx': i
                })
            
            # Check for missing text
            if not segment.original_text and not segment.translated_text:
                issues.append({
                    'type': 'warning',
                    'message': 'Segment has no text',
                    'segment_idx': i
                })
            
            # Update for next iteration
            prev_end = segment.end_time
        
        return issues
    
    def embed_subtitles_in_video(self, video_path: str, output_path: str,
                                format_type: str = 'srt') -> str:
        """
        Embed subtitles directly into a video file.
        
        Args:
            video_path: Path to the input video file
            output_path: Path to save the output video
            format_type: Subtitle format to use for embedding
            
        Returns:
            Path to the output video file
            
        Raises:
            ValueError: If ffmpeg is not available or other error occurs
        """
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"Video file not found: {video_path}")
            
        if not self.segments:
            raise ValueError("No subtitle segments to embed")
        
        # Create a temporary subtitle file
        with tempfile.NamedTemporaryFile(suffix=f".{format_type}", delete=False) as tmp_file:
            subtitle_path = tmp_file.name
        
        try:
            # Save subtitles to the temp file
            self.save_to_file(subtitle_path, format_type)
            
            # Prepare FFmpeg command
            cmd = [
                self.ffmpeg_path,
                '-i', video_path,             # Input video
                '-i', subtitle_path,          # Input subtitle
                '-c:v', 'copy',               # Copy video stream
                '-c:a', 'copy',               # Copy audio stream
                '-c:s', 'mov_text' if output_path.lower().endswith('.mp4') else 'copy',  # Subtitle codec
                '-map', '0:v',                # Map video from first input
                '-map', '0:a?',               # Map audio from first input if exists
                '-map', '1',                  # Map subtitles from second input
                '-y',                         # Overwrite output
                output_path                   # Output file
            ]
            
            # Execute FFmpeg command
            logger.info(f"Embedding subtitles using command: {' '.join(cmd)}")
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode != 0:
                logger.error(f"Failed to embed subtitles: {result.stderr}")
                raise ValueError(f"FFmpeg error: {result.stderr}")
                
            logger.info(f"Successfully embedded subtitles into {output_path}")
            return output_path
            
        finally:
            # Clean up temporary file
            try:
                os.unlink(subtitle_path)
            except Exception as e:
                logger.warning(f"Failed to delete temporary subtitle file: {e}")
    
    def burn_subtitles_into_video(self, video_path: str, output_path: str,
                                 font_size: int = 24, font_color: str = 'white',
                                 position: str = 'bottom') -> str:
        """
        Burn subtitles directly into the video (hardcode).
        
        Args:
            video_path: Path to the input video file
            output_path: Path to save the output video
            font_size: Font size for subtitles
            font_color: Font color for subtitles
            position: Position of subtitles ('bottom', 'top', 'middle')
            
        Returns:
            Path to the output video file
            
        Raises:
            ValueError: If ffmpeg is not available or other error occurs
        """
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"Video file not found: {video_path}")
            
        if not self.segments:
            raise ValueError("No subtitle segments to burn")
        
        # Create a temporary subtitle file (using ASS for better style control)
        with tempfile.NamedTemporaryFile(suffix=".ass", delete=False) as tmp_file:
            subtitle_path = tmp_file.name
        
        try:
            # Configure subtitle position
            if position == 'top':
                pos_value = '2'  # Top-center
            elif position == 'middle':
                pos_value = '5'  # Middle-center
            else:
                pos_value = '2'  # Bottom-center (default)
            
            # Apply styles for burn-in
            for segment in self.segments:
                if segment.style is None:
                    segment.style = {}
                segment.style.update({
                    'alignment': pos_value,
                    'fontsize': str(font_size),
                    'primarycolour': font_color
                })
            
            # Save subtitles to the temp file
            self.save_to_file(subtitle_path, 'ass')
            
            # Prepare FFmpeg command
            cmd = [
                self.ffmpeg_path,
                '-i', video_path,             # Input video
                '-vf', f"ass={subtitle_path}",  # Apply subtitles as filter
                '-c:a', 'copy',               # Copy audio stream
                '-y',                         # Overwrite output
                output_path                   # Output file
            ]
            
            # Execute FFmpeg command
            logger.info(f"Burning subtitles using command: {' '.join(cmd)}")
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode != 0:
                logger.error(f"Failed to burn subtitles: {result.stderr}")
                raise ValueError(f"FFmpeg error: {result.stderr}")
                
            logger.info(f"Successfully burned subtitles into {output_path}")
            return output_path
            
        finally:
            # Clean up temporary file
            try:
                os.unlink(subtitle_path)
            except Exception as e:
                logger.warning(f"Failed to delete temporary subtitle file: {e}")
    
    def extract_subtitles_from_video(self, video_path: str) -> Optional[List[SubtitleSegment]]:
        """
        Extract embedded subtitles from a video file.
        
        Args:
            video_path: Path to the video file
            
        Returns:
            List of extracted subtitle segments or None if no subtitles found
        """
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"Video file not found: {video_path}")
        
        # Create a temporary subtitle file
        with tempfile.NamedTemporaryFile(suffix=".srt", delete=False) as tmp_file:
            subtitle_path = tmp_file.name
        
        try:
            # Prepare FFmpeg command to extract subtitles
            cmd = [
                self.ffmpeg_path,
                '-i', video_path,             # Input video
                '-map', '0:s:0',              # Map first subtitle stream
                '-c:s', 'srt',                # Convert to SRT
                '-y',                         # Overwrite output
                subtitle_path                 # Output file
            ]
            
            # Execute FFmpeg command
            logger.info(f"Extracting subtitles using command: {' '.join(cmd)}")
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode != 0:
                # Check if the error is because no subtitle stream was found
                if "Stream map '0:s:0' matches no streams" in result.stderr:
                    logger.info("No subtitle stream found in the video")
                    return None
                else:
                    logger.error(f"Failed to extract subtitles: {result.stderr}")
                    raise ValueError(f"FFmpeg error: {result.stderr}")
            
            # Load the extracted subtitles
            try:
                extracted_segments = self.load_from_file(subtitle_path)
                logger.info(f"Successfully extracted {len(extracted_segments)} subtitle segments")
                return extracted_segments
            except Exception as e:
                logger.warning(f"Failed to parse extracted subtitles: {e}")
                return None
                
        finally:
            # Clean up temporary file
            try:
                os.unlink(subtitle_path)
            except Exception as e:
                logger.warning(f"Failed to delete temporary subtitle file: {e}")