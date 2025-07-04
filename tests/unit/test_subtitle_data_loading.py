#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试字幕编辑器的数据加载问题
"""

import unittest
import json
import tempfile
import os
from unittest.mock import Mock, MagicMock, patch
from app.core.subtitle import SubtitleSegment, SubtitleProcessor
from app.config import AppConfig


class TestSubtitleEditorDataLoading(unittest.TestCase):
    """测试字幕编辑器数据加载问题"""
    
    def test_segments_data_format(self):
        """测试segments数据格式"""
        # 模拟处理完成的结果数据
        processing_result = {
            'video_path': 'test.mp4',
            'segments': [
                {
                    'start': 0.0,
                    'end': 2.0,
                    'original_text': 'Hello world',
                    'translated_text': '你好世界'
                },
                {
                    'start': 2.0,
                    'end': 4.0,
                    'original_text': 'How are you?',
                    'translated_text': '你好吗？'
                }
            ]
        }
        
        # 测试字幕处理器能否正确处理这种格式
        processor = SubtitleProcessor()
        segments = processor.create_from_segments(processing_result['segments'])
        
        # 验证结果
        self.assertEqual(len(segments), 2)
        self.assertEqual(segments[0].start_time, 0.0)
        self.assertEqual(segments[0].end_time, 2.0)
        self.assertEqual(segments[0].original_text, 'Hello world')
        self.assertEqual(segments[0].translated_text, '你好世界')
        
        print("✓ 字幕处理器正确处理了segments数据")
    
    def test_project_file_format(self):
        """测试项目文件格式"""
        # 创建一些测试的字幕段
        segments = [
            SubtitleSegment(0.0, 2.0, 'Hello world', '你好世界', 1),
            SubtitleSegment(2.0, 4.0, 'How are you?', '你好吗？', 2)
        ]
        
        # 模拟项目文件保存
        import dataclasses
        project_data = [dataclasses.asdict(seg) for seg in segments]
        
        # 创建临时文件
        with tempfile.NamedTemporaryFile(mode='w', suffix='.vtp', delete=False) as f:
            json.dump(project_data, f, ensure_ascii=False, indent=2)
            temp_path = f.name
        
        try:
            # 读取项目文件
            with open(temp_path, 'r', encoding='utf-8') as f:
                loaded_data = json.load(f)
            
            # 验证数据结构
            self.assertEqual(len(loaded_data), 2)
            self.assertIn('start_time', loaded_data[0])
            self.assertIn('end_time', loaded_data[0])
            self.assertIn('original_text', loaded_data[0])
            self.assertIn('translated_text', loaded_data[0])
            
            # 测试字幕处理器是否能处理这种格式
            processor = SubtitleProcessor()
            segments = processor.create_from_segments(loaded_data)
            
            self.assertEqual(len(segments), 2)
            self.assertEqual(segments[0].original_text, 'Hello world')
            self.assertEqual(segments[0].translated_text, '你好世界')
            
            print("✓ 项目文件格式正确，字幕处理器能正确加载")
            
        finally:
            os.unlink(temp_path)
    
    def test_processing_result_vs_project_data(self):
        """测试处理结果和项目数据的不同格式"""
        # 处理结果格式（新版本）
        processing_result = {
            'segments': [
                {
                    'start': 0.0,
                    'end': 2.0,
                    'original_text': 'Hello world',
                    'translated_text': '你好世界'
                }
            ]
        }
        
        # 项目文件格式（保存后的格式）
        project_segment = SubtitleSegment(0.0, 2.0, 'Hello world', '你好世界', 1)
        import dataclasses
        project_data = [dataclasses.asdict(project_segment)]
        
        print("处理结果格式:", processing_result['segments'][0])
        print("项目文件格式:", project_data[0])
        
        # 测试两种格式都能被字幕处理器处理
        processor1 = SubtitleProcessor()
        segments1 = processor1.create_from_segments(processing_result['segments'])
        
        processor2 = SubtitleProcessor()
        segments2 = processor2.create_from_segments(project_data)
        
        # 验证结果相同
        self.assertEqual(segments1[0].original_text, segments2[0].original_text)
        self.assertEqual(segments1[0].translated_text, segments2[0].translated_text)
        
        print("✓ 两种格式都能被正确处理")
    
    def test_improved_processing_segments_format(self):
        """测试改进的处理器生成的segments格式"""
        # 模拟语音识别结果
        recognition_result = {
            'segments': [
                {'start': 0.0, 'end': 2.0, 'text': 'Hello world'},
                {'start': 2.0, 'end': 4.0, 'text': 'How are you?'}
            ]
        }
        
        # 模拟翻译结果
        translation_result = {
            'translated_texts': ['你好世界', '你好吗？']
        }
        
        # 模拟improved_processing.py中的segments构建逻辑
        segments_data = []
        if recognition_result and 'segments' in recognition_result:
            original_segments = recognition_result['segments']
            translated_texts = translation_result.get('translated_texts', [])
            
            # 组合原始段和翻译文本
            for i, segment in enumerate(original_segments):
                translated_text = translated_texts[i] if i < len(translated_texts) else ''
                segments_data.append({
                    'start': segment.get('start', 0),
                    'end': segment.get('end', 0),
                    'original_text': segment.get('text', ''),
                    'translated_text': translated_text
                })
        
        # 验证构建的segments数据
        self.assertEqual(len(segments_data), 2)
        self.assertEqual(segments_data[0]['start'], 0.0)
        self.assertEqual(segments_data[0]['end'], 2.0)
        self.assertEqual(segments_data[0]['original_text'], 'Hello world')
        self.assertEqual(segments_data[0]['translated_text'], '你好世界')
        
        # 测试字幕处理器能否处理这种格式
        processor = SubtitleProcessor()
        segments = processor.create_from_segments(segments_data)
        
        self.assertEqual(len(segments), 2)
        self.assertEqual(segments[0].original_text, 'Hello world')
        self.assertEqual(segments[0].translated_text, '你好世界')
        
        print("✓ 改进的处理器生成的segments格式正确")


if __name__ == '__main__':
    print("开始测试字幕编辑器数据加载...")
    unittest.main(verbosity=2)
