#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
诊断视频切换时VLC全屏播放问题的脚本
"""

import logging

# 设置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def diagnose_video_switching_issue():
    """诊断视频切换时的VLC问题"""
    print("=== 视频切换时VLC全屏播放问题诊断 ===\n")
    
    print("问题场景:")
    print("1. 从零开始打开视频 → 正常工作，视频在字幕编辑器中正常显示")
    print("2. 已经打开视频后，再打开新视频 → VLC全屏播放，不在字幕编辑器中")
    print()
    
    print("可能的根本原因:")
    print("1. 旧的VLC实例没有正确释放")
    print("2. 窗口句柄在视频切换时丢失")
    print("3. VLC播放器重用时窗口绑定失效")
    print("4. Qt窗口状态在视频切换时不稳定")
    print("5. 全屏检查定时器在视频切换时产生冲突")
    print()
    
    print("需要检查的代码区域:")
    print("- load_data() 方法中的VLC实例清理")
    print("- _init_vlc_playback() 方法中的实例创建")
    print("- 视频切换时的窗口状态管理")
    print("- 定时器的清理和重新创建")
    print()
    
    print("建议的修复策略:")
    print("1. 在加载新视频前完全清理旧的VLC实例")
    print("2. 重新获取窗口句柄")
    print("3. 重置所有相关的定时器")
    print("4. 强制窗口重新获取焦点")
    print("5. 添加视频切换特定的调试日志")

if __name__ == "__main__":
    diagnose_video_switching_issue()
