#!/usr/bin/env python3
"""
测试修复后的硬字幕烧入功能
"""

import os
import sys
import tempfile
import logging
import subprocess
from pathlib import Path

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.core.video import VideoProcessor

def create_test_video():
    """创建一个简单的测试视频"""
    # 创建临时视频文件（仅用于测试路径，实际不会创建视频）
    temp_dir = tempfile.gettempdir()
    test_video = os.path.join(temp_dir, "test_video.mp4")
    
    # 使用 ffmpeg 创建一个简单的测试视频
    try:
        import subprocess
        subprocess.run([
            'ffmpeg', '-f', 'lavfi', '-i', 'testsrc=duration=10:size=320x240:rate=1',
            '-pix_fmt', 'yuv420p', '-y', test_video
        ], check=True, capture_output=True, timeout=30)
        
        if os.path.exists(test_video):
            print(f"✅ 创建测试视频: {test_video}")
            return test_video
        else:
            print("❌ 测试视频创建失败")
            return None
    except Exception as e:
        print(f"❌ 创建测试视频失败: {e}")
        return None

def create_test_srt():
    """创建测试SRT字幕文件"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.srt', delete=False, encoding='utf-8') as f:
        f.write("""1
00:00:01,000 --> 00:00:05,000
这是第一条测试字幕

2
00:00:06,000 --> 00:00:10,000
这是第二条测试字幕
""")
        return f.name

def test_burn_with_real_files():
    """使用真实文件测试硬字幕烧入"""
    print("=== 使用真实文件测试硬字幕烧入 ===")
    
    # 设置详细日志
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
    
    # 检查 FFmpeg
    processor = VideoProcessor()
    if not processor.check_ffmpeg_available():
        print("❌ FFmpeg 不可用")
        return False
    
    print("✅ FFmpeg 可用")
    
    # 创建测试文件
    test_video = create_test_video()
    if not test_video:
        print("❌ 无法创建测试视频，跳过真实文件测试")
        return False
    
    test_srt = create_test_srt()
    print(f"✅ 创建测试字幕: {test_srt}")
    
    # 创建输出路径
    output_dir = tempfile.gettempdir()
    output_video = os.path.join(output_dir, "test_output_with_subs.mp4")
    
    try:
        print(f"开始烧入字幕测试...")
        print(f"输入视频: {test_video}")
        print(f"输入字幕: {test_srt}")
        print(f"输出视频: {output_video}")
        
        # 执行烧入
        success = processor.burn_subtitles_to_video(
            test_video,
            test_srt,
            output_video
        )
        
        if success:
            print("✅ 硬字幕烧入成功!")
            print(f"输出文件: {output_video}")
            
            # 检查输出文件大小
            if os.path.exists(output_video):
                size = os.path.getsize(output_video)
                print(f"输出文件大小: {size} bytes")
                
                # 验证输出文件是否有效
                try:
                    probe_result = subprocess.run([
                        'ffprobe', '-v', 'quiet', '-print_format', 'json', 
                        '-show_format', output_video
                    ], capture_output=True, text=True)
                    
                    if probe_result.returncode == 0:
                        print("✅ 输出视频文件格式有效")
                    else:
                        print("❌ 输出视频文件格式无效")
                        
                except Exception as e:
                    print(f"❌ 验证输出文件时出错: {e}")
            else:
                print("❌ 输出文件不存在")
                return False
        else:
            print("❌ 硬字幕烧入失败")
            return False
            
    except Exception as e:
        print(f"❌ 测试过程中出错: {e}")
        return False
        
    finally:
        # 清理测试文件
        try:
            if os.path.exists(test_video):
                os.unlink(test_video)
            if os.path.exists(test_srt):
                os.unlink(test_srt)
            if os.path.exists(output_video):
                os.unlink(output_video)
            print("✅ 清理测试文件完成")
        except Exception as e:
            print(f"清理文件时出错: {e}")
    
    return True

def test_error_handling():
    """测试错误处理"""
    print("\n=== 测试错误处理 ===")
    
    processor = VideoProcessor()
    
    # 测试不存在的文件
    result = processor.burn_subtitles_to_video(
        "non_existent_video.mp4",
        "non_existent_subtitle.srt",
        "output.mp4"
    )
    
    if not result:
        print("✅ 正确处理不存在的文件")
    else:
        print("❌ 错误处理失败")
        return False
    
    return True

def main():
    """主测试函数"""
    print("=== 硬字幕烧入功能全面测试 ===")
    
    # 测试1: 错误处理
    if not test_error_handling():
        print("❌ 错误处理测试失败")
        return
    
    # 测试2: 真实文件测试
    if not test_burn_with_real_files():
        print("❌ 真实文件测试失败")
        return
    
    print("\n=== 所有测试完成 ===")
    print("✅ 硬字幕烧入功能修复成功!")

if __name__ == "__main__":
    main()
