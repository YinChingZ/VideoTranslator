#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
简化的字幕生成修复测试
"""

import unittest
import tempfile
import os
from unittest.mock import Mock, MagicMock, patch
from app.config import AppConfig


class TestSubtitleGenerationFix(unittest.TestCase):
    """测试字幕生成修复"""
    
    def test_subtitle_generation_result_type(self):
        """测试字幕生成结果类型处理"""
        # 导入改进的处理器
        from app.gui.improved_processing import ImprovedProcessingWorker
        
        # 创建配置
        config = AppConfig()
        
        # 创建工作器
        worker = ImprovedProcessingWorker(
            video_path="test.mp4",
            source_language="en",
            target_language="zh",
            config=config
        )
        
        # 模拟字幕处理器
        worker.subtitle_processor = Mock()
        worker.subtitle_processor.create_from_segments.return_value = ["segment1", "segment2"]
        worker.subtitle_processor.save_to_file.return_value = "/tmp/test_subtitles.srt"
        
        # 模拟检查点管理器
        worker.checkpoint_manager = Mock()
        
        # 模拟翻译结果
        translation_result = {
            'segments': [
                {'text': 'Hello world', 'start': 0, 'end': 1},
                {'text': 'How are you', 'start': 1, 'end': 2}
            ]
        }
        
        # 测试字幕生成
        try:
            result = worker.subtitle_generation_stage(translation_result)
            
            # 验证结果是字符串
            self.assertIsInstance(result, str)
            self.assertTrue(result.endswith('.srt'))
            
            print(f"✓ 字幕生成成功，结果类型: {type(result)}")
            print(f"✓ 字幕文件路径: {result}")
            
        except Exception as e:
            self.fail(f"字幕生成失败: {e}")
    
    def test_os_path_basename_with_string(self):
        """测试 os.path.basename 与字符串参数"""
        import os
        
        # 测试字符串路径
        test_path = "/tmp/test_subtitles.srt"
        basename = os.path.basename(test_path)
        self.assertEqual(basename, "test_subtitles.srt")
        
        # 测试 Windows 路径
        test_path_win = "C:\\temp\\test_subtitles.srt"
        basename_win = os.path.basename(test_path_win)
        self.assertEqual(basename_win, "test_subtitles.srt")
        
        print("✓ os.path.basename 与字符串参数正常工作")
    
    def test_os_path_basename_with_list_error(self):
        """测试 os.path.basename 与列表参数的错误"""
        import os
        
        # 测试列表参数应该抛出 TypeError
        test_list = ["file1.srt", "file2.srt"]
        
        with self.assertRaises(TypeError) as cm:
            os.path.basename(test_list)
        
        self.assertIn("expected str, bytes or os.PathLike object, not list", str(cm.exception))
        print("✓ os.path.basename 与列表参数正确抛出 TypeError")


if __name__ == '__main__':
    print("开始测试字幕生成修复...")
    unittest.main(verbosity=2)
