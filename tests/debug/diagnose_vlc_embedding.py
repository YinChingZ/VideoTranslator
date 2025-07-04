#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
诊断VLC全屏播放问题的脚本
"""

import logging
import sys
import os

# 设置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def diagnose_vlc_embedding_issue():
    """诊断VLC嵌入问题"""
    print("=== VLC嵌入模式诊断 ===\n")
    
    try:
        import vlc
        print("✓ VLC模块导入成功")
        
        # 检查VLC版本
        print(f"VLC版本: {vlc.libvlc_get_version().decode()}")
        
        # 测试VLC参数
        print("\n--- 当前VLC初始化参数 ---")
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
        
        for arg in vlc_args:
            print(f"  {arg}")
        
        print("\n--- 问题分析 ---")
        print("可能的原因:")
        print("1. VLC实例创建时窗口句柄未正确设置")
        print("2. --embedded-video 参数不起作用")
        print("3. 窗口绑定在媒体加载之前失效")
        print("4. Qt窗口属性配置问题")
        print("5. 事件处理顺序问题")
        
        print("\n--- 建议的调试步骤 ---")
        print("1. 检查窗口句柄获取是否成功")
        print("2. 验证VLC播放器窗口绑定")
        print("3. 检查媒体加载顺序")
        print("4. 添加更多调试日志")
        print("5. 测试不同的VLC参数组合")
        
        print("\n--- 增强修复建议 ---")
        print("应该在以下位置添加调试信息:")
        print("- 窗口句柄获取后")
        print("- VLC播放器创建后")
        print("- 窗口绑定后")
        print("- 媒体加载后")
        print("- 播放开始后")
        
    except Exception as e:
        print(f"✗ 诊断失败: {e}")

if __name__ == "__main__":
    diagnose_vlc_embedding_issue()
