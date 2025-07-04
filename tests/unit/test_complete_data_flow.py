#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
综合测试：验证从处理到显示的完整数据流程
"""

import unittest
import json
import tempfile
import os
from unittest.mock import Mock, MagicMock, patch
from app.core.subtitle import SubtitleSegment, SubtitleProcessor
from app.config import AppConfig


class TestCompleteDataFlow(unittest.TestCase):
    """测试完整的数据流程"""
    
    def test_processing_to_editor_flow(self):
        """测试从处理完成到编辑器加载的完整流程"""
        print("\n=== 测试处理到编辑器流程 ===")
        
        # 1. 模拟语音识别结果
        recognition_result = {
            'segments': [
                {'start': 0.0, 'end': 2.0, 'text': 'Hello world'},
                {'start': 2.0, 'end': 4.0, 'text': 'How are you?'},
                {'start': 4.0, 'end': 6.0, 'text': 'Good morning'}
            ]
        }
        print("✓ 语音识别结果模拟完成")
        
        # 2. 模拟翻译结果
        translation_result = {
            'translated_texts': ['你好世界', '你好吗？', '早上好']
        }
        print("✓ 翻译结果模拟完成")
        
        # 3. 模拟improved_processing.py中的segments构建
        segments_data = []
        if recognition_result and 'segments' in recognition_result:
            original_segments = recognition_result['segments']
            translated_texts = translation_result.get('translated_texts', [])
            
            for i, segment in enumerate(original_segments):
                translated_text = translated_texts[i] if i < len(translated_texts) else ''
                segments_data.append({
                    'start': segment.get('start', 0),
                    'end': segment.get('end', 0),
                    'original_text': segment.get('text', ''),
                    'translated_text': translated_text
                })
        
        print(f"✓ 构建了 {len(segments_data)} 个字幕段")
        
        # 4. 模拟processing_complete的结果数据
        result_data = {
            'video_path': 'test.mp4',
            'segments': segments_data,
            'status': 'completed'
        }
        print("✓ 处理完成结果数据构建完成")
        
        # 5. 模拟字幕编辑器的load_data过程
        raw_segments = result_data.get("segments", [])
        
        # 使用字幕处理器处理数据
        processor = SubtitleProcessor()
        subtitle_segments = processor.create_from_segments(raw_segments)
        
        print(f"✓ 字幕处理器处理了 {len(subtitle_segments)} 个字幕段")
        
        # 6. 验证结果
        self.assertEqual(len(subtitle_segments), 3)
        
        # 验证每个字幕段的内容
        expected_data = [
            (0.0, 2.0, 'Hello world', '你好世界'),
            (2.0, 4.0, 'How are you?', '你好吗？'),
            (4.0, 6.0, 'Good morning', '早上好')
        ]
        
        for i, (start, end, orig, trans) in enumerate(expected_data):
            segment = subtitle_segments[i]
            self.assertEqual(segment.start_time, start, f"Segment {i+1} start time")
            self.assertEqual(segment.end_time, end, f"Segment {i+1} end time")
            self.assertEqual(segment.original_text, orig, f"Segment {i+1} original text")
            self.assertEqual(segment.translated_text, trans, f"Segment {i+1} translated text")
        
        print("✓ 所有字幕段验证通过")
        
        # 7. 模拟字幕显示逻辑
        def find_subtitle_at_time(segments, position):
            for segment in segments:
                if segment.start_time <= position <= segment.end_time:
                    return segment
            return None
        
        # 测试不同时间点的字幕显示
        test_positions = [1.0, 3.0, 5.0, 7.0]
        expected_texts = ['你好世界', '你好吗？', '早上好', None]
        
        for pos, expected in zip(test_positions, expected_texts):
            current_segment = find_subtitle_at_time(subtitle_segments, pos)
            if expected is None:
                self.assertIsNone(current_segment, f"Position {pos} should have no subtitle")
            else:
                self.assertIsNotNone(current_segment, f"Position {pos} should have subtitle")
                self.assertEqual(current_segment.translated_text, expected, 
                               f"Position {pos} should show '{expected}'")
        
        print("✓ 字幕显示逻辑验证通过")
        
    def test_project_save_and_load_flow(self):
        """测试项目保存和加载流程"""
        print("\n=== 测试项目保存和加载流程 ===")
        
        # 1. 创建测试字幕段
        segments = [
            SubtitleSegment(0.0, 2.0, 'Hello world', '你好世界', 1),
            SubtitleSegment(2.0, 4.0, 'How are you?', '你好吗？', 2),
            SubtitleSegment(4.0, 6.0, 'Good morning', '早上好', 3)
        ]
        print(f"✓ 创建了 {len(segments)} 个字幕段")
        
        # 2. 模拟项目保存
        import dataclasses
        project_data = [dataclasses.asdict(seg) for seg in segments]
        
        # 保存到临时文件
        with tempfile.NamedTemporaryFile(mode='w', suffix='.vtp', delete=False) as f:
            json.dump(project_data, f, ensure_ascii=False, indent=2)
            temp_path = f.name
        
        print(f"✓ 项目保存到 {temp_path}")
        
        try:
            # 3. 模拟项目加载
            with open(temp_path, 'r', encoding='utf-8') as f:
                loaded_data = json.load(f)
            
            print(f"✓ 从项目文件加载了 {len(loaded_data)} 个字幕段")
            
            # 4. 模拟字幕编辑器的load_data过程（项目加载）
            result_data = {
                'video_path': 'test.mp4',
                'segments': loaded_data,
                'is_project_import': True
            }
            
            # 使用字幕处理器处理项目数据
            processor = SubtitleProcessor()
            loaded_segments = processor.create_from_segments(loaded_data)
            
            print(f"✓ 字幕处理器处理了 {len(loaded_segments)} 个字幕段")
            
            # 5. 验证加载的数据与原始数据一致
            self.assertEqual(len(loaded_segments), len(segments))
            
            for i, (original, loaded) in enumerate(zip(segments, loaded_segments)):
                self.assertEqual(original.start_time, loaded.start_time, f"Segment {i+1} start time")
                self.assertEqual(original.end_time, loaded.end_time, f"Segment {i+1} end time")
                self.assertEqual(original.original_text, loaded.original_text, f"Segment {i+1} original text")
                self.assertEqual(original.translated_text, loaded.translated_text, f"Segment {i+1} translated text")
            
            print("✓ 项目数据加载验证通过")
            
        finally:
            # 清理临时文件
            os.unlink(temp_path)
    
    def test_checkpoint_recovery_flow(self):
        """测试检查点恢复流程"""
        print("\n=== 测试检查点恢复流程 ===")
        
        # 1. 模拟检查点数据
        checkpoint_data = {
            'speech_recognition': {
                'recognition_result': {
                    'segments': [
                        {'start': 0.0, 'end': 2.0, 'text': 'Hello world'},
                        {'start': 2.0, 'end': 4.0, 'text': 'How are you?'}
                    ]
                }
            },
            'text_translation': {
                'translation_result': {
                    'translated_texts': ['你好世界', '你好吗？']
                }
            }
        }
        print("✓ 检查点数据模拟完成")
        
        # 2. 模拟从检查点恢复segments构建
        recognition_result = checkpoint_data['speech_recognition']['recognition_result']
        translation_result = checkpoint_data['text_translation']['translation_result']
        
        segments_data = []
        if recognition_result and 'segments' in recognition_result:
            original_segments = recognition_result['segments']
            translated_texts = translation_result.get('translated_texts', [])
            
            for i, segment in enumerate(original_segments):
                translated_text = translated_texts[i] if i < len(translated_texts) else ''
                segments_data.append({
                    'start': segment.get('start', 0),
                    'end': segment.get('end', 0),
                    'original_text': segment.get('text', ''),
                    'translated_text': translated_text
                })
        
        print(f"✓ 从检查点恢复构建了 {len(segments_data)} 个字幕段")
        
        # 3. 验证恢复的数据
        processor = SubtitleProcessor()
        recovered_segments = processor.create_from_segments(segments_data)
        
        self.assertEqual(len(recovered_segments), 2)
        self.assertEqual(recovered_segments[0].original_text, 'Hello world')
        self.assertEqual(recovered_segments[0].translated_text, '你好世界')
        self.assertEqual(recovered_segments[1].original_text, 'How are you?')
        self.assertEqual(recovered_segments[1].translated_text, '你好吗？')
        
        print("✓ 检查点恢复验证通过")


if __name__ == '__main__':
    print("开始测试完整数据流程...")
    unittest.main(verbosity=2)
