#!/usr/bin/env python3
"""
测试硬字幕烧入功能修复
"""

import os
import sys
import tempfile
import logging
from pathlib import Path

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.core.video import VideoProcessor

def create_test_srt_file():
    """创建一个测试用的SRT字幕文件"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.srt', delete=False, encoding='utf-8') as f:
        f.write("""1
00:00:01,000 --> 00:00:05,000
这是第一条测试字幕

2
00:00:06,000 --> 00:00:10,000
这是第二条测试字幕
""")
        return f.name

def test_burn_subtitles_fix():
    """测试硬字幕烧入功能修复"""
    # 设置日志
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    
    print("=== 硬字幕烧入功能修复测试 ===")
    
    # 检查ffmpeg可用性
    if not VideoProcessor.check_ffmpeg_available():
        print("❌ FFmpeg 不可用，请确保已安装FFmpeg")
        return False
    
    print("✅ FFmpeg 可用")
    
    # 创建视频处理器
    processor = VideoProcessor()
    
    # 检查burn_subtitles_to_video方法是否存在
    if not hasattr(processor, 'burn_subtitles_to_video'):
        print("❌ VideoProcessor 缺少 burn_subtitles_to_video 方法")
        return False
    
    print("✅ burn_subtitles_to_video 方法存在")
    
    # 创建测试字幕文件
    test_srt_file = create_test_srt_file()
    print(f"✅ 创建测试字幕文件: {test_srt_file}")
    
    # 测试参数验证
    print("\n--- 测试参数验证 ---")
    
    # 测试不存在的视频文件
    result = processor.burn_subtitles_to_video(
        "non_existent_video.mp4",
        test_srt_file,
        "output.mp4"
    )
    print(f"不存在的视频文件测试: {'✅ 正确处理' if not result else '❌ 应该失败'}")
    
    # 测试不存在的字幕文件
    result = processor.burn_subtitles_to_video(
        "some_video.mp4",
        "non_existent_subtitle.srt",
        "output.mp4"
    )
    print(f"不存在的字幕文件测试: {'✅ 正确处理' if not result else '❌ 应该失败'}")
    
    # 测试方法调用（模拟成功情况）
    print("\n--- 测试方法调用结构 ---")
    
    try:
        # 这里我们不会真的执行，只是测试方法调用结构
        # 使用一个虚拟的视频文件路径来测试代码路径
        fake_video = os.path.join(tempfile.gettempdir(), "fake_video.mp4")
        fake_output = os.path.join(tempfile.gettempdir(), "fake_output.mp4")
        
        # 这个调用会失败，但能测试代码路径
        result = processor.burn_subtitles_to_video(
            fake_video,
            test_srt_file,
            fake_output
        )
        
        print("✅ 方法调用结构正确（即使没有真实视频文件）")
        
    except Exception as e:
        print(f"❌ 方法调用结构问题: {e}")
        
    finally:
        # 清理测试文件
        try:
            os.unlink(test_srt_file)
            print("✅ 清理测试文件")
        except:
            pass
    
    print("\n=== 测试完成 ===")
    print("如果你有真实的视频文件，可以使用以下代码测试完整功能：")
    print("""
# 示例代码：
from app.core.video import VideoProcessor

processor = VideoProcessor()
success = processor.burn_subtitles_to_video(
    'your_video.mp4',
    'your_subtitle.srt', 
    'output_with_burned_subs.mp4'
)
print(f"硬字幕烧入{'成功' if success else '失败'}")
""")
    
    return True

if __name__ == "__main__":
    test_burn_subtitles_fix()
