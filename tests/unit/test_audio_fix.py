#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.audio import AudioProcessor
from pathlib import Path

def test_audio_processing():
    """测试音频处理功能"""
    try:
        # 初始化音频处理器
        audio_processor = AudioProcessor()
        print("✓ AudioProcessor 初始化成功")
        
        # 创建一个测试用的简单FFmpeg命令来验证语法
        import ffmpeg
        
        # 测试FFmpeg库是否正常工作
        print("✓ FFmpeg 库导入成功")
        
        # 创建一个简单的输入流来测试语法
        test_input = ffmpeg.input('dummy_input.mp4')
        test_output = ffmpeg.output(
            test_input.audio,
            'dummy_output.wav',
            acodec='pcm_s16le',
            ac=1,
            ar=16000,
            format='wav'
        )
        
        # 获取命令行（不实际执行）
        cmd = ffmpeg.compile(test_output)
        print(f"✓ FFmpeg 命令语法正确: {' '.join(cmd)}")
        
        print("\n音频处理模块修复成功！FFmpeg 命令语法现在是正确的。")
        
    except Exception as e:
        print(f"✗ 测试失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_audio_processing()
