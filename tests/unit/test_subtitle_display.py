#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试字幕显示功能
"""

import unittest
import sys
import os
from unittest.mock import Mock, MagicMock, patch

# 模拟PyQt5环境
sys.modules['PyQt5'] = MagicMock()
sys.modules['PyQt5.QtCore'] = MagicMock()
sys.modules['PyQt5.QtWidgets'] = MagicMock()
sys.modules['PyQt5.QtGui'] = MagicMock()
sys.modules['PyQt5.QtMultimedia'] = MagicMock()
sys.modules['PyQt5.QtMultimediaWidgets'] = MagicMock()
sys.modules['cv2'] = MagicMock()

from app.core.subtitle import SubtitleSegment, SubtitleProcessor
from app.config import AppConfig


class TestSubtitleDisplay(unittest.TestCase):
    """测试字幕显示功能"""
    
    def setUp(self):
        """设置测试环境"""
        self.segments = [
            SubtitleSegment(0.0, 2.0, 'Hello world', '你好世界', 1),
            SubtitleSegment(2.0, 4.0, 'How are you?', '你好吗？', 2),
            SubtitleSegment(4.0, 6.0, 'Good morning', '早上好', 3)
        ]
    
    def test_subtitle_timing_logic(self):
        """测试字幕时间匹配逻辑"""
        # 模拟update_subtitle_display的核心逻辑
        def find_current_subtitle(segments, position):
            for segment in segments:
                if segment.start_time <= position <= segment.end_time:
                    return segment
            return None
        
        # 测试不同时间点的字幕
        test_cases = [
            (0.5, '你好世界'),    # 在第一个字幕时间内
            (1.5, '你好世界'),    # 在第一个字幕时间内
            (2.5, '你好吗？'),    # 在第二个字幕时间内
            (3.5, '你好吗？'),    # 在第二个字幕时间内
            (4.5, '早上好'),      # 在第三个字幕时间内
            (6.5, None),         # 超出所有字幕时间
            (-0.5, None),        # 小于所有字幕时间
        ]
        
        for position, expected in test_cases:
            current_segment = find_current_subtitle(self.segments, position)
            if expected is None:
                self.assertIsNone(current_segment, f"Position {position} should have no subtitle")
            else:
                self.assertIsNotNone(current_segment, f"Position {position} should have a subtitle")
                self.assertEqual(current_segment.translated_text, expected, 
                               f"Position {position} should show '{expected}'")
        
        print("✓ 字幕时间匹配逻辑正确")
    
    def test_subtitle_display_text_formatting(self):
        """测试字幕显示文本格式"""
        segment = self.segments[0]
        
        # 测试不同的显示模式
        test_cases = [
            (True, True, "Hello world\n\n你好世界"),    # 显示原文和译文
            (True, False, "Hello world"),              # 仅显示原文
            (False, True, "你好世界"),                 # 仅显示译文
            (False, False, ""),                        # 都不显示
        ]
        
        for show_original, show_translation, expected in test_cases:
            # 模拟字幕显示逻辑
            display_text = ""
            
            if show_original and segment.original_text:
                display_text += segment.original_text
                
            if show_translation and segment.translated_text:
                if display_text:  # Add newline if we already have original text
                    display_text += "\n\n"
                display_text += segment.translated_text
            
            self.assertEqual(display_text, expected, 
                           f"Show original: {show_original}, Show translation: {show_translation}")
        
        print("✓ 字幕显示文本格式正确")
    
    def test_subtitle_processor_segments_handling(self):
        """测试字幕处理器的段数据处理"""
        # 测试不同格式的输入数据
        test_data_formats = [
            # 处理结果格式
            [
                {
                    'start': 0.0,
                    'end': 2.0,
                    'original_text': 'Hello world',
                    'translated_text': '你好世界'
                }
            ],
            # 项目文件格式
            [
                {
                    'start_time': 0.0,
                    'end_time': 2.0,
                    'original_text': 'Hello world',
                    'translated_text': '你好世界',
                    'index': 1,
                    'style': {}
                }
            ],
            # 语音识别+翻译格式
            [
                {
                    'start': 0.0,
                    'end': 2.0,
                    'text': 'Hello world',
                    'translation': '你好世界'
                }
            ]
        ]
        
        for i, data_format in enumerate(test_data_formats):
            processor = SubtitleProcessor()
            segments = processor.create_from_segments(data_format)
            
            self.assertEqual(len(segments), 1, f"Format {i+1} should create 1 segment")
            self.assertEqual(segments[0].start_time, 0.0, f"Format {i+1} start time should be 0.0")
            self.assertEqual(segments[0].end_time, 2.0, f"Format {i+1} end time should be 2.0")
            self.assertEqual(segments[0].original_text, 'Hello world', f"Format {i+1} original text should match")
            self.assertEqual(segments[0].translated_text, '你好世界', f"Format {i+1} translated text should match")
        
        print("✓ 字幕处理器正确处理不同格式的数据")
    
    def test_empty_segments_handling(self):
        """测试空字幕数据的处理"""
        # 测试空列表
        processor = SubtitleProcessor()
        segments = processor.create_from_segments([])
        self.assertEqual(len(segments), 0, "Empty list should create no segments")
        
        # 测试包含空字段的数据
        empty_data = [
            {
                'start': 0.0,
                'end': 2.0,
                'original_text': '',
                'translated_text': ''
            }
        ]
        
        segments = processor.create_from_segments(empty_data)
        self.assertEqual(len(segments), 1, "Should create segment even with empty text")
        self.assertEqual(segments[0].original_text, '', "Empty original text should be preserved")
        self.assertEqual(segments[0].translated_text, '', "Empty translated text should be preserved")
        
        print("✓ 空字幕数据处理正确")


if __name__ == '__main__':
    print("开始测试字幕显示功能...")
    unittest.main(verbosity=2)
