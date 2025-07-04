#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试字幕生成阶段的修复
"""

import os
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch, MagicMock

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.gui.improved_processing import ImprovedProcessingWorker
from app.core.subtitle import SubtitleProcessor


class TestSubtitleGenerationFix(unittest.TestCase):
    def setUp(self):
        """设置测试环境"""
        self.video_path = "test_video.mp4"
        self.output_dir = tempfile.mkdtemp()
        
        # 创建模拟对象
        self.mock_video_processor = Mock()
        self.mock_audio_processor = Mock()
        self.mock_speech_recognizer = Mock()
        self.mock_translator = Mock()
        self.mock_subtitle_processor = Mock()
        self.mock_checkpoint_manager = Mock()
        self.mock_memory_manager = Mock()
        
        # 创建处理器
        self.worker = ImprovedProcessingWorker(
            video_path=self.video_path,
            output_dir=self.output_dir,
            video_processor=self.mock_video_processor,
            audio_processor=self.mock_audio_processor,
            speech_recognizer=self.mock_speech_recognizer,
            translator=self.mock_translator,
            subtitle_processor=self.mock_subtitle_processor,
            checkpoint_manager=self.mock_checkpoint_manager,
            memory_manager=self.mock_memory_manager
        )
    
    def test_subtitle_generation_normal_case(self):
        """测试正常情况下的字幕生成"""
        # 准备测试数据
        translation_result = {
            'original_segments': [
                {'start': 0, 'end': 5, 'text': 'Hello world'},
                {'start': 5, 'end': 10, 'text': 'How are you?'}
            ],
            'translated_texts': ['你好世界', '你好吗？']
        }
        
        # 设置模拟返回值
        expected_path = os.path.join(tempfile.gettempdir(), "test_video_subtitles.srt")
        self.mock_subtitle_processor.save_to_file.return_value = expected_path
        
        # 运行测试
        result = self.worker.subtitle_generation_stage(translation_result)
        
        # 验证结果
        self.assertIsInstance(result, str)
        self.assertEqual(result, expected_path)
        
        # 验证调用
        self.mock_subtitle_processor.create_from_segments.assert_called_once()
        self.mock_subtitle_processor.save_to_file.assert_called_once()
        self.mock_checkpoint_manager.save_checkpoint.assert_called_once()
    
    def test_subtitle_generation_with_list_result(self):
        """测试当结果意外返回列表时的处理"""
        # 准备测试数据
        translation_result = {
            'original_segments': [
                {'start': 0, 'end': 5, 'text': 'Hello world'}
            ],
            'translated_texts': ['你好世界']
        }
        
        # 模拟run_stage_with_timeout返回列表（这是错误情况）
        with patch.object(self.worker, 'run_stage_with_timeout') as mock_run_stage:
            mock_run_stage.return_value = ['segment1', 'segment2']  # 意外返回列表
            
            expected_path = os.path.join(tempfile.gettempdir(), "test_video_subtitles.srt")
            self.mock_subtitle_processor.save_to_file.return_value = expected_path
            
            # 运行测试
            result = self.worker.subtitle_generation_stage(translation_result)
            
            # 验证结果
            self.assertIsInstance(result, str)
            self.assertEqual(result, expected_path)
            
            # 验证save_to_file被调用了两次（一次在generate_subtitles中，一次在修复代码中）
            self.assertEqual(self.mock_subtitle_processor.save_to_file.call_count, 1)
    
    def test_subtitle_segments_creation(self):
        """测试字幕段的创建"""
        # 准备测试数据
        translation_result = {
            'original_segments': [
                {'start': 0, 'end': 5, 'text': 'Hello'},
                {'start': 5, 'end': 10, 'text': 'World'}
            ],
            'translated_texts': ['你好', '世界']
        }
        
        expected_path = os.path.join(tempfile.gettempdir(), "test_video_subtitles.srt")
        self.mock_subtitle_processor.save_to_file.return_value = expected_path
        
        # 运行测试
        result = self.worker.subtitle_generation_stage(translation_result)
        
        # 验证create_from_segments被调用，并检查传入的参数
        self.mock_subtitle_processor.create_from_segments.assert_called_once()
        call_args = self.mock_subtitle_processor.create_from_segments.call_args[0][0]
        
        # 验证传入的字幕段数据
        self.assertEqual(len(call_args), 2)
        self.assertEqual(call_args[0]['start'], 0)
        self.assertEqual(call_args[0]['end'], 5)
        self.assertEqual(call_args[0]['text'], '你好')
        self.assertEqual(call_args[1]['start'], 5)
        self.assertEqual(call_args[1]['end'], 10)
        self.assertEqual(call_args[1]['text'], '世界')
    
    def test_subtitle_generation_with_empty_data(self):
        """测试空数据的处理"""
        # 准备测试数据
        translation_result = {
            'original_segments': [],
            'translated_texts': []
        }
        
        expected_path = os.path.join(tempfile.gettempdir(), "test_video_subtitles.srt")
        self.mock_subtitle_processor.save_to_file.return_value = expected_path
        
        # 运行测试
        result = self.worker.subtitle_generation_stage(translation_result)
        
        # 验证结果
        self.assertIsInstance(result, str)
        self.assertEqual(result, expected_path)
        
        # 验证create_from_segments被调用，传入空列表
        self.mock_subtitle_processor.create_from_segments.assert_called_once_with([])


def main():
    """运行测试"""
    unittest.main(verbosity=2)


if __name__ == '__main__':
    main()
