#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试修复后的字幕生成功能，模拟原始错误情况
"""

import unittest
import logging
import tempfile
import os
from unittest.mock import Mock, MagicMock, patch
from app.config import AppConfig


class TestSubtitleGenerationErrorFix(unittest.TestCase):
    """测试字幕生成错误修复"""
    
    def test_subtitle_generation_with_list_result_error(self):
        """测试当subtitle_processor返回列表时的错误处理"""
        # 导入改进的处理器
        from app.gui.improved_processing import ImprovedProcessingWorker
        
        # 创建配置
        config = AppConfig()
        
        # 创建工作器
        worker = ImprovedProcessingWorker(
            video_path="testvidep.mp4",
            source_language="en",
            target_language="zh",
            config=config
        )
        
        # 模拟字幕处理器返回列表（模拟原始错误）
        worker.subtitle_processor = Mock()
        worker.subtitle_processor.create_from_segments.return_value = ["segment1", "segment2"]
        worker.subtitle_processor.save_to_file.return_value = "/tmp/testvidep_subtitles.srt"
        
        # 模拟检查点管理器
        worker.checkpoint_manager = Mock()
        
        # 模拟日志发射器
        worker.log = Mock()
        worker.progress = Mock()
        
        # 模拟翻译结果
        translation_result = {
            'original_segments': [
                {'text': 'Hello world', 'start': 0.0, 'end': 1.0},
                {'text': 'How are you', 'start': 1.0, 'end': 2.0}
            ],
            'translated_texts': [
                '你好世界',
                '你好吗'
            ]
        }
        
        # 模拟run_stage_with_timeout返回列表（模拟原始错误情况）
        def mock_run_stage_with_timeout(stage_name, func):
            # 模拟意外返回列表的情况
            if stage_name == 'subtitle_generation':
                # 这里模拟原始错误：返回列表而不是字符串
                return ["segment1", "segment2"]
            return func()
        
        worker.run_stage_with_timeout = mock_run_stage_with_timeout
        
        # 测试字幕生成
        try:
            result = worker.subtitle_generation_stage(translation_result)
            
            # 验证结果是字符串
            self.assertIsInstance(result, str)
            self.assertTrue(result.endswith('.srt'))
            
            # 验证日志记录了警告
            # 在实际修复中，应该会有警告日志
            
            print(f"✓ 字幕生成成功处理了列表结果，最终结果类型: {type(result)}")
            print(f"✓ 字幕文件路径: {result}")
            
        except Exception as e:
            self.fail(f"字幕生成失败: {e}")
    
    def test_os_path_basename_error_reproduction(self):
        """重现原始的 os.path.basename 错误"""
        import os
        
        # 模拟原始错误场景
        result = ["segment1", "segment2"]  # 这是导致错误的列表
        
        # 这应该抛出 TypeError
        with self.assertRaises(TypeError) as cm:
            basename = os.path.basename(result)
        
        error_msg = str(cm.exception)
        self.assertIn("expected str, bytes or os.PathLike object, not list", error_msg)
        
        print(f"✓ 成功重现原始错误: {error_msg}")
    
    def test_subtitle_generation_normal_flow(self):
        """测试正常的字幕生成流程"""
        # 导入改进的处理器
        from app.gui.improved_processing import ImprovedProcessingWorker
        
        # 创建配置
        config = AppConfig()
        
        # 创建工作器
        worker = ImprovedProcessingWorker(
            video_path="testvidep.mp4",
            source_language="en",
            target_language="zh",
            config=config
        )
        
        # 模拟字幕处理器正常返回
        worker.subtitle_processor = Mock()
        worker.subtitle_processor.create_from_segments.return_value = ["segment1", "segment2"]
        worker.subtitle_processor.save_to_file.return_value = "/tmp/testvidep_subtitles.srt"
        
        # 模拟检查点管理器
        worker.checkpoint_manager = Mock()
        
        # 模拟日志发射器
        worker.log = Mock()
        worker.progress = Mock()
        
        # 模拟翻译结果
        translation_result = {
            'original_segments': [
                {'text': 'Hello world', 'start': 0.0, 'end': 1.0},
                {'text': 'How are you', 'start': 1.0, 'end': 2.0}
            ],
            'translated_texts': [
                '你好世界',
                '你好吗'
            ]
        }
        
        # 模拟run_stage_with_timeout正常返回字符串
        def mock_run_stage_with_timeout(stage_name, func):
            if stage_name == 'subtitle_generation':
                return "/tmp/testvidep_subtitles.srt"
            return func()
        
        worker.run_stage_with_timeout = mock_run_stage_with_timeout
        
        # 测试字幕生成
        try:
            result = worker.subtitle_generation_stage(translation_result)
            
            # 验证结果是字符串
            self.assertIsInstance(result, str)
            self.assertTrue(result.endswith('.srt'))
            
            # 验证日志调用
            worker.log.emit.assert_called()
            
            print(f"✓ 正常字幕生成成功，结果类型: {type(result)}")
            print(f"✓ 字幕文件路径: {result}")
            
        except Exception as e:
            self.fail(f"字幕生成失败: {e}")


if __name__ == '__main__':
    print("开始测试字幕生成错误修复...")
    
    # 设置日志级别
    logging.basicConfig(level=logging.INFO)
    
    unittest.main(verbosity=2)
