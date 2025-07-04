#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
检查VLC字幕轨道相关API和可能的内嵌字幕控制逻辑
"""

import logging

# 设置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def check_vlc_subtitle_apis():
    """检查VLC中与字幕相关的API"""
    print("=== VLC字幕相关API检查 ===\n")
    
    try:
        import vlc
        print("✓ VLC模块导入成功")
        
        # 创建VLC实例进行API检查
        instance = vlc.Instance(['--quiet'])
        player = instance.media_player_new()
        
        print("\n--- 字幕轨道相关方法 ---")
        subtitle_methods = [
            'video_get_spu_count',      # 获取字幕轨道数量
            'video_get_spu',            # 获取当前字幕轨道
            'video_set_spu',            # 设置字幕轨道
            'video_get_spu_description', # 获取字幕轨道描述
        ]
        
        for method in subtitle_methods:
            if hasattr(player, method):
                print(f"✓ {method} - 可用")
            else:
                print(f"✗ {method} - 不可用")
        
        print("\n--- 常用VLC字幕控制参数 ---")
        vlc_subtitle_options = [
            '--no-sub-autodetect-file',  # 禁用字幕文件自动检测
            '--sub-track',               # 选择字幕轨道
            '--no-spu',                  # 禁用所有字幕
            '--sub-file',                # 指定字幕文件
            '--sub-filter',              # 字幕过滤器
        ]
        
        for option in vlc_subtitle_options:
            print(f"• {option}")
        
        print("\n--- 测试字幕轨道信息获取 ---")
        
        # 如果有可用的视频文件，可以测试
        test_video_path = None
        
        # 尝试查找测试视频文件
        import os
        possible_paths = [
            r"d:\Projects\VideoTranslator\testvidep.mp4",
            r"d:\Projects\VideoTranslator\test.mp4",
        ]
        
        for path in possible_paths:
            if os.path.exists(path):
                test_video_path = path
                break
        
        if test_video_path:
            print(f"找到测试视频: {test_video_path}")
            
            # 加载媒体
            media = instance.media_new(test_video_path)
            player.set_media(media)
            
            # 需要先播放才能获取轨道信息
            player.play()
            
            import time
            time.sleep(2)  # 等待媒体加载
            
            # 获取字幕轨道信息
            if hasattr(player, 'video_get_spu_count'):
                spu_count = player.video_get_spu_count()
                print(f"字幕轨道数量: {spu_count}")
                
                if hasattr(player, 'video_get_spu'):
                    current_spu = player.video_get_spu()
                    print(f"当前字幕轨道: {current_spu}")
                
                if hasattr(player, 'video_get_spu_description'):
                    spu_desc = player.video_get_spu_description()
                    print(f"字幕轨道描述: {spu_desc}")
                
                # 测试禁用字幕
                if hasattr(player, 'video_set_spu'):
                    print("\n尝试禁用字幕...")
                    player.video_set_spu(-1)  # -1 通常表示禁用字幕
                    time.sleep(1)
                    new_spu = player.video_get_spu() if hasattr(player, 'video_get_spu') else "未知"
                    print(f"设置后的字幕轨道: {new_spu}")
            
            player.stop()
        else:
            print("未找到测试视频文件，跳过实际测试")
        
        print("\n=== 可能的解决方案 ===")
        print("1. 在VLC初始化参数中添加 '--no-spu' 来禁用所有字幕")
        print("2. 在视频加载后调用 player.video_set_spu(-1) 来禁用字幕轨道")
        print("3. 添加 '--no-sub-autodetect-file' 来防止自动加载外部字幕文件")
        
    except ImportError:
        print("✗ VLC模块未找到")
    except Exception as e:
        print(f"✗ 检查过程中出错: {e}")

def analyze_subtitle_editor_logic():
    """分析字幕编辑器中可能的内嵌字幕逻辑"""
    print("\n=== 字幕编辑器逻辑分析 ===\n")
    
    print("根据代码分析，可能的内嵌字幕显示条件:")
    print("1. 视频文件本身包含内嵌字幕轨道")
    print("2. VLC默认启用了第一个可用的字幕轨道")
    print("3. 没有显式禁用VLC的字幕显示功能")
    print("4. 视频格式支持内嵌字幕（如MP4, MKV等）")
    
    print("\n当前VLC初始化参数:")
    vlc_args = [
        '--intf', 'dummy',
        '--no-video-title-show',
        '--no-video-deco',
        '--embedded-video',
        '--no-fullscreen',
        '--no-keyboard-events',
        '--no-mouse-events',
        '--no-xlib'
    ]
    
    for arg in vlc_args:
        print(f"  {arg}")
    
    print("\n注意: 当前参数中没有字幕相关的控制选项!")

if __name__ == '__main__':
    check_vlc_subtitle_apis()
    analyze_subtitle_editor_logic()
    
    print("\n=== 建议的修复方案 ===")
    print("在 VLC 初始化参数中添加以下选项来禁用内嵌字幕:")
    print("'--no-spu'                    # 禁用所有字幕")
    print("'--no-sub-autodetect-file'    # 禁用字幕文件自动检测")
    print("\n或在视频加载后调用:")
    print("player.video_set_spu(-1)      # 禁用当前字幕轨道")
