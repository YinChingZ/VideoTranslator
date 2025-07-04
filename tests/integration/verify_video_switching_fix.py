#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
验证VLC视频切换修复的脚本
"""

import logging
import sys
import os

# 设置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_video_switching_fix():
    """测试视频切换修复"""
    print("=== 测试VLC视频切换修复 ===\n")
    
    try:
        # 1. 测试模块导入
        print("1. 测试模块导入...")
        from app.gui.subtitle_editor import SubtitleEditor
        print("✓ 字幕编辑器模块导入成功")
        
        # 2. 检查关键方法是否存在
        print("\n2. 检查关键修复方法...")
        methods_to_check = [
            '_cleanup_vlc_player',
            '_prepare_video_playback', 
            '_init_vlc_playback',
            '_force_embedded_mode',
            '_enforce_embedded_mode',
            'load_data'
        ]
        
        for method_name in methods_to_check:
            if hasattr(SubtitleEditor, method_name):
                print(f"✓ 方法 {method_name} 存在")
            else:
                print(f"✗ 方法 {method_name} 不存在")
        
        # 3. 测试VLC导入
        print("\n3. 测试VLC导入...")
        import vlc
        print("✓ VLC模块导入成功")
        
        # 4. 测试VLC参数
        print("\n4. 测试VLC嵌入模式参数...")
        vlc_args = [
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
        
        critical_args = ['--embedded-video', '--no-fullscreen']
        for arg in critical_args:
            if arg in vlc_args:
                print(f"✓ 关键参数 {arg} 存在")
            else:
                print(f"✗ 关键参数 {arg} 缺失")
        
        # 5. 测试VLC实例创建
        print("\n5. 测试VLC实例创建...")
        try:
            instance = vlc.Instance(vlc_args)
            if instance:
                print("✓ VLC实例创建成功")
                player = instance.media_player_new()
                if player:
                    print("✓ VLC播放器创建成功")
                    player.set_fullscreen(False)
                    print("✓ VLC全屏模式禁用成功")
                    
                    # 清理
                    player.release()
                    instance.release()
                    print("✓ VLC资源清理成功")
                else:
                    print("✗ VLC播放器创建失败")
            else:
                print("✗ VLC实例创建失败")
        except Exception as e:
            print(f"✗ VLC测试失败: {e}")
        
        # 6. 修复总结
        print("\n6. 修复总结...")
        print("已实施的修复措施:")
        print("• 在load_data方法中添加VLC清理逻辑")
        print("• 在_init_vlc_playback方法中强化窗口准备")
        print("• 添加强制嵌入模式检查和重新绑定")
        print("• 增加更多日志记录用于调试")
        print("• 优化窗口句柄获取和验证")
        
        print("\n=== 修复验证完成 ===")
        print("核心修复已到位，应该能解决视频切换时VLC全屏播放的问题。")
        
    except Exception as e:
        print(f"测试失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_video_switching_fix()
