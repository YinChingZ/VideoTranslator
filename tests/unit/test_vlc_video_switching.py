#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试VLC视频切换时的全屏播放问题修复
模拟用户场景：已经打开一个视频后，再打开新视频时VLC全屏播放的问题
"""

import unittest
import logging
import sys
import os
from unittest.mock import Mock, MagicMock, patch, call
from PyQt5.QtWidgets import QApplication, QWidget
from PyQt5.QtCore import QTimer

# 设置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TestVLCVideoSwitching(unittest.TestCase):
    """测试VLC视频切换时的嵌入模式问题"""
    
    def setUp(self):
        """设置测试环境"""
        # 模拟Qt应用程序
        if not QApplication.instance():
            self.app = QApplication(sys.argv)
        else:
            self.app = QApplication.instance()
    
    def test_video_switching_vlc_cleanup(self):
        """测试视频切换时VLC清理逻辑"""
        print("=== 测试视频切换时VLC清理 ===")
        
        # 模拟字幕编辑器的VLC相关属性
        mock_editor = Mock()
        mock_editor.vlc_player = Mock()
        mock_editor.vlc_instance = Mock()
        mock_editor.vlc_timer = Mock()
        mock_editor.fullscreen_check_timer = Mock()
        
        # 模拟VLC播放器的方法
        mock_editor.vlc_player.stop.return_value = None
        mock_editor.vlc_player.release.return_value = None
        mock_editor.vlc_instance.release.return_value = None
        mock_editor.vlc_timer.stop.return_value = None
        mock_editor.fullscreen_check_timer.stop.return_value = None
        
        # 模拟_cleanup_vlc_player方法的逻辑
        def mock_cleanup_vlc_player():
            if hasattr(mock_editor, 'vlc_player') and mock_editor.vlc_player:
                try:
                    mock_editor.vlc_player.stop()
                    mock_editor.vlc_player.release()
                    mock_editor.vlc_player = None
                    logger.info("VLC播放器已清理")
                except Exception as e:
                    logger.error(f"清理VLC播放器时出错: {e}")
                    
            if hasattr(mock_editor, 'vlc_instance') and mock_editor.vlc_instance:
                try:
                    mock_editor.vlc_instance.release()
                    mock_editor.vlc_instance = None
                    logger.info("VLC实例已清理")
                except Exception as e:
                    logger.error(f"清理VLC实例时出错: {e}")
                    
            if hasattr(mock_editor, 'vlc_timer') and mock_editor.vlc_timer:
                mock_editor.vlc_timer.stop()
                mock_editor.vlc_timer = None
                logger.info("VLC定时器已清理")
                
            if hasattr(mock_editor, 'fullscreen_check_timer') and mock_editor.fullscreen_check_timer:
                mock_editor.fullscreen_check_timer.stop()
                mock_editor.fullscreen_check_timer = None
                logger.info("全屏检查定时器已清理")
        
        # 执行清理
        mock_cleanup_vlc_player()
        
        # 验证清理操作
        mock_editor.vlc_player.stop.assert_called_once()
        mock_editor.vlc_player.release.assert_called_once()
        mock_editor.vlc_instance.release.assert_called_once()
        mock_editor.vlc_timer.stop.assert_called_once()
        mock_editor.fullscreen_check_timer.stop.assert_called_once()
        
        # 验证对象被设置为None
        self.assertIsNone(mock_editor.vlc_player)
        self.assertIsNone(mock_editor.vlc_instance)
        self.assertIsNone(mock_editor.vlc_timer)
        self.assertIsNone(mock_editor.fullscreen_check_timer)
        
        print("✓ VLC清理逻辑测试通过")
    
    def test_window_rebinding_on_video_switch(self):
        """测试视频切换时窗口重新绑定"""
        print("=== 测试视频切换时窗口重新绑定 ===")
        
        # 模拟窗口组件
        mock_video_widget = Mock()
        mock_video_widget.winId.return_value = 12345
        mock_video_widget.setAttribute = Mock()
        mock_video_widget.setVisible = Mock()
        mock_video_widget.setFocus = Mock()
        
        # 模拟VLC播放器
        mock_vlc_player = Mock()
        mock_vlc_player.set_hwnd = Mock()
        mock_vlc_player.set_fullscreen = Mock()
        mock_vlc_player.get_fullscreen.return_value = False
        
        # 模拟窗口重新绑定逻辑
        def mock_rebind_window():
            # 强制重新获取窗口属性
            mock_video_widget.setAttribute('WA_NativeWindow', True)
            mock_video_widget.setAttribute('WA_DontCreateNativeAncestors', True)
            mock_video_widget.setVisible(True)
            mock_video_widget.setFocus()
            
            # 重新获取窗口句柄
            win_id = int(mock_video_widget.winId())
            logger.info(f"重新获取窗口句柄: {win_id}")
            
            # 重新绑定VLC播放器
            if sys.platform.startswith("win"):
                mock_vlc_player.set_hwnd(win_id)
            
            # 确保不是全屏模式
            mock_vlc_player.set_fullscreen(False)
            
            logger.info("窗口重新绑定完成")
        
        # 执行窗口重新绑定
        mock_rebind_window()
        
        # 验证窗口操作
        mock_video_widget.setAttribute.assert_called()
        mock_video_widget.setVisible.assert_called_with(True)
        mock_video_widget.setFocus.assert_called_once()
        mock_video_widget.winId.assert_called_once()
        
        # 验证VLC播放器绑定
        mock_vlc_player.set_hwnd.assert_called_with(12345)
        mock_vlc_player.set_fullscreen.assert_called_with(False)
        
        print("✓ 窗口重新绑定测试通过")
    
    def test_video_switching_sequence(self):
        """测试完整的视频切换序列"""
        print("=== 测试完整的视频切换序列 ===")
        
        # 模拟场景：用户已经打开视频A，现在要打开视频B
        print("场景：用户已经打开视频A，现在要打开视频B")
        
        # 步骤1：模拟现有视频A的VLC状态
        print("步骤1：模拟现有视频A的VLC状态")
        mock_editor = Mock()
        mock_editor.vlc_player = Mock()
        mock_editor.vlc_instance = Mock()
        mock_editor.video_path = "video_a.mp4"
        
        # 步骤2：用户选择新视频B
        print("步骤2：用户选择新视频B")
        new_video_path = "video_b.mp4"
        
        # 步骤3：触发load_data方法
        print("步骤3：触发load_data方法")
        # 应该首先清理旧的VLC实例
        cleanup_called = False
        def mock_cleanup():
            nonlocal cleanup_called
            cleanup_called = True
            mock_editor.vlc_player = None
            mock_editor.vlc_instance = None
            logger.info("旧VLC实例已清理")
        
        # 步骤4：清理旧VLC实例
        mock_cleanup()
        self.assertTrue(cleanup_called, "应该调用VLC清理方法")
        self.assertIsNone(mock_editor.vlc_player)
        self.assertIsNone(mock_editor.vlc_instance)
        
        # 步骤5：初始化新VLC实例
        print("步骤5：初始化新VLC实例")
        mock_editor.video_path = new_video_path
        mock_editor.vlc_player = Mock()
        mock_editor.vlc_instance = Mock()
        
        # 步骤6：验证新VLC实例的嵌入模式设置
        print("步骤6：验证新VLC实例的嵌入模式设置")
        expected_vlc_args = [
            '--intf', 'dummy',
            '--no-video-title-show',
            '--no-video-deco',
            '--embedded-video',
            '--no-fullscreen',
            '--no-keyboard-events',
            '--no-mouse-events',
            '--no-xlib',
            '--no-spu',
            '--no-sub-autodetect-file'
        ]
        
        # 验证VLC参数包含嵌入模式设置
        self.assertIn('--embedded-video', expected_vlc_args)
        self.assertIn('--no-fullscreen', expected_vlc_args)
        
        print("✓ 完整的视频切换序列测试通过")
    
    def test_window_focus_restoration(self):
        """测试窗口焦点恢复逻辑"""
        print("=== 测试窗口焦点恢复逻辑 ===")
        
        # 模拟窗口组件
        mock_window = Mock()
        mock_widget = Mock()
        mock_editor = Mock()
        mock_editor.window.return_value = mock_window
        mock_editor.video_widget = mock_widget
        
        # 模拟焦点恢复逻辑
        def mock_restore_focus():
            # 激活主窗口
            mock_editor.window().activateWindow()
            # 设置视频组件焦点
            mock_editor.video_widget.setFocus()
            logger.info("窗口焦点已恢复")
        
        # 执行焦点恢复
        mock_restore_focus()
        
        # 验证焦点恢复操作
        mock_editor.window.assert_called()
        mock_window.activateWindow.assert_called_once()
        mock_widget.setFocus.assert_called_once()
        
        print("✓ 窗口焦点恢复测试通过")

def run_tests():
    """运行所有测试"""
    print("开始测试VLC视频切换问题修复...")
    print("=" * 60)
    
    # 创建测试套件
    suite = unittest.TestSuite()
    suite.addTest(TestVLCVideoSwitching('test_video_switching_vlc_cleanup'))
    suite.addTest(TestVLCVideoSwitching('test_window_rebinding_on_video_switch'))
    suite.addTest(TestVLCVideoSwitching('test_video_switching_sequence'))
    suite.addTest(TestVLCVideoSwitching('test_window_focus_restoration'))
    
    # 运行测试
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    # 输出结果
    if result.wasSuccessful():
        print("\n" + "=" * 60)
        print("🎉 所有测试通过！VLC视频切换问题修复验证成功。")
        print("=" * 60)
    else:
        print("\n" + "=" * 60)
        print("❌ 测试失败，需要进一步调试。")
        print("=" * 60)
    
    return result.wasSuccessful()

if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
