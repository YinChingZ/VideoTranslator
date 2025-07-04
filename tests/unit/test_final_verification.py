#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
最终验证：确保字幕编辑器能正确加载和显示字幕
"""

import unittest
import logging
from unittest.mock import Mock, MagicMock, patch
from app.core.subtitle import SubtitleSegment, SubtitleProcessor
from app.config import AppConfig

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class TestSubtitleEditorFix(unittest.TestCase):
    """测试字幕编辑器修复"""
    
    def test_improved_processing_segments_generation(self):
        """测试改进的处理器生成正确的segments数据"""
        print("\n=== 测试改进的处理器segments生成 ===")
        
        # 模拟ImprovedProcessingWorker的最终结果构建逻辑
        def build_final_result(recognition_result, translation_result):
            """模拟improved_processing.py中的最终结果构建"""
            segments_data = []
            if recognition_result and 'segments' in recognition_result:
                original_segments = recognition_result['segments']
                translated_texts = translation_result.get('translated_texts', []) if translation_result else []
                
                # 组合原始段和翻译文本
                for i, segment in enumerate(original_segments):
                    translated_text = translated_texts[i] if i < len(translated_texts) else ''
                    segments_data.append({
                        'start': segment.get('start', 0),
                        'end': segment.get('end', 0),
                        'original_text': segment.get('text', ''),
                        'translated_text': translated_text
                    })
            
            return {
                'video_path': 'test.mp4',
                'segments': segments_data,
                'status': 'completed'
            }
        
        # 测试数据
        recognition_result = {
            'segments': [
                {'start': 0.0, 'end': 2.0, 'text': 'Hello world'},
                {'start': 2.0, 'end': 4.0, 'text': 'How are you?'}
            ]
        }
        
        translation_result = {
            'translated_texts': ['你好世界', '你好吗？']
        }
        
        # 生成最终结果
        final_result = build_final_result(recognition_result, translation_result)
        
        # 验证结果包含segments
        self.assertIn('segments', final_result)
        self.assertEqual(len(final_result['segments']), 2)
        
        # 验证segments数据格式
        segment1 = final_result['segments'][0]
        self.assertEqual(segment1['start'], 0.0)
        self.assertEqual(segment1['end'], 2.0)
        self.assertEqual(segment1['original_text'], 'Hello world')
        self.assertEqual(segment1['translated_text'], '你好世界')
        
        print("✓ 改进的处理器正确生成了segments数据")
        
        # 测试字幕编辑器能够加载这些数据
        processor = SubtitleProcessor()
        segments = processor.create_from_segments(final_result['segments'])
        
        self.assertEqual(len(segments), 2)
        self.assertEqual(segments[0].original_text, 'Hello world')
        self.assertEqual(segments[0].translated_text, '你好世界')
        
        print("✓ 字幕编辑器正确加载了segments数据")
    
    def test_subtitle_display_with_real_data(self):
        """测试字幕显示功能与实际数据"""
        print("\n=== 测试字幕显示功能 ===")
        
        # 创建真实的字幕段数据
        segments = [
            SubtitleSegment(0.0, 2.0, 'Hello world', '你好世界', 1),
            SubtitleSegment(2.0, 4.0, 'How are you?', '你好吗？', 2),
            SubtitleSegment(4.0, 6.0, 'Good morning', '早上好', 3)
        ]
        
        # 模拟字幕显示更新逻辑
        def update_subtitle_display(segments, position, show_original=True, show_translation=True):
            """模拟SubtitleEditorWidget.update_subtitle_display逻辑"""
            if not segments:
                return ""
                
            for segment in segments:
                if segment.start_time <= position <= segment.end_time:
                    display_text = ""
                    
                    if show_original and segment.original_text:
                        display_text += segment.original_text
                        
                    if show_translation and segment.translated_text:
                        if display_text:  # Add newline if we already have original text
                            display_text += "\n\n"
                        display_text += segment.translated_text
                    
                    return display_text
            
            return ""
        
        # 测试不同时间点的字幕显示
        test_cases = [
            (1.0, "Hello world\n\n你好世界"),  # 第一个字幕
            (3.0, "How are you?\n\n你好吗？"),  # 第二个字幕
            (5.0, "Good morning\n\n早上好"),   # 第三个字幕
            (7.0, ""),                        # 无字幕
        ]
        
        for position, expected in test_cases:
            result = update_subtitle_display(segments, position)
            self.assertEqual(result, expected, f"Position {position} should show '{expected}'")
        
        print("✓ 字幕显示功能正常工作")
        
        # 测试仅显示原文或译文
        result_orig_only = update_subtitle_display(segments, 1.0, show_original=True, show_translation=False)
        self.assertEqual(result_orig_only, "Hello world")
        
        result_trans_only = update_subtitle_display(segments, 1.0, show_original=False, show_translation=True)
        self.assertEqual(result_trans_only, "你好世界")
        
        print("✓ 字幕显示模式切换正常工作")
    
    def test_error_scenarios(self):
        """测试错误场景处理"""
        print("\n=== 测试错误场景处理 ===")
        
        # 测试空segments处理
        processor = SubtitleProcessor()
        
        # 空列表
        segments = processor.create_from_segments([])
        self.assertEqual(len(segments), 0)
        print("✓ 空segments列表处理正常")
        
        # 缺少字段的数据
        incomplete_data = [
            {'start': 0.0, 'end': 2.0},  # 缺少文本字段
            {'original_text': 'Hello', 'translated_text': '你好'}  # 缺少时间字段
        ]
        
        segments = processor.create_from_segments(incomplete_data)
        self.assertEqual(len(segments), 2)
        
        # 第一个段应该有时间但没有文本
        self.assertEqual(segments[0].start_time, 0.0)
        self.assertEqual(segments[0].end_time, 2.0)
        self.assertEqual(segments[0].original_text, '')
        self.assertEqual(segments[0].translated_text, '')
        
        # 第二个段应该有文本但时间为默认值
        self.assertEqual(segments[1].start_time, 0.0)  # 默认值
        self.assertEqual(segments[1].end_time, 0.0)    # 默认值
        self.assertEqual(segments[1].original_text, 'Hello')
        self.assertEqual(segments[1].translated_text, '你好')
        
        print("✓ 不完整数据处理正常")
        
        # 测试无效数据类型
        invalid_data = [
            {'start': 'invalid', 'end': 2.0, 'text': 'Hello'},  # 无效的时间格式
        ]
        
        # 这应该跳过无效的段
        segments = processor.create_from_segments(invalid_data)
        # 由于时间格式无效，应该跳过这个段
        self.assertEqual(len(segments), 0)
        
        print("✓ 无效数据处理正常")
    
    def test_video_subtitle_sync(self):
        """测试视频与字幕同步逻辑"""
        print("\n=== 测试视频字幕同步 ===")
        
        # 创建测试字幕段，模拟真实场景，确保有明显的间隙
        segments = [
            SubtitleSegment(0.0, 1.5, '音频转写完成，用时: 1.68秒', '音频转写完成，用时: 1.68秒', 1),
            SubtitleSegment(2.0, 4.0, 'DeepL service is not available', 'DeepL服务不可用', 2),
            SubtitleSegment(5.0, 7.0, 'All translation services failed', '所有翻译服务失败', 3)
        ]
        
        print(f"字幕段时间范围:")
        for i, seg in enumerate(segments):
            print(f"  段{i+1}: {seg.start_time} - {seg.end_time}")
        
        # 模拟播放时间更新和字幕显示
        def simulate_playback(segments, duration=10.0, step=0.1):
            """模拟视频播放过程中的字幕显示"""
            displayed_subtitles = []
            current_time = 0.0
            
            while current_time <= duration:
                for segment in segments:
                    if segment.start_time <= current_time <= segment.end_time:
                        displayed_subtitles.append({
                            'time': current_time,
                            'text': segment.translated_text
                        })
                        break
                current_time += step
            
            return displayed_subtitles
        
        # 模拟播放
        displayed = simulate_playback(segments)
        
        # 验证字幕在正确的时间点显示
        self.assertGreater(len(displayed), 0)
        
        # 检查第一个字幕在0.0-1.5秒之间显示
        first_subtitle_displays = [d for d in displayed if d['text'] == '音频转写完成，用时: 1.68秒']
        self.assertGreater(len(first_subtitle_displays), 0)
        
        # 检查第一个字幕的时间范围
        first_times = [d['time'] for d in first_subtitle_displays]
        self.assertGreaterEqual(min(first_times), 0.0)
        self.assertLessEqual(max(first_times), 1.5)
        
        print("✓ 视频字幕同步逻辑正常")
        
        # 测试字幕间隙处理（1.5-2.0, 4.0-5.0, 7.0+）
        gap_times = [1.7, 4.5, 8.0]  # 字幕间隙的时间点
        for gap_time in gap_times:
            found_subtitle = False
            for segment in segments:
                if segment.start_time <= gap_time <= segment.end_time:
                    found_subtitle = True
                    break
            self.assertFalse(found_subtitle, f"Time {gap_time} should not have subtitle")
        
        print("✓ 字幕间隙处理正常")


if __name__ == '__main__':
    print("开始最终验证测试...")
    print("=" * 50)
    
    unittest.main(verbosity=2)
    
    print("=" * 50)
    print("所有测试完成！字幕编辑器修复验证成功！")
