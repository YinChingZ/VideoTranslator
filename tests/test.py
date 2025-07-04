#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
System diagnostics tool for VideoTranslator
检查系统环境和依赖项的诊断工具
"""

import struct
import os
import sys
import platform
import subprocess
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from datetime import datetime


def check_python_environment() -> Dict[str, str]:
    """检查Python环境信息"""
    python_bits = struct.calcsize("P") * 8
    return {
        "python_version": platform.python_version(),
        "python_bits": f"{python_bits}位",
        "platform": platform.platform(),
        "architecture": platform.architecture()[0],
        "executable": sys.executable
    }


def check_vlc_installation() -> Dict[str, Optional[str]]:
    """检查VLC媒体播放器安装情况"""
    vlc_paths = [
        r"C:\Program Files\VideoLAN\VLC\libvlc.dll",
        r"C:\Program Files (x86)\VideoLAN\VLC\libvlc.dll",
        "/usr/lib/x86_64-linux-gnu/libvlc.so.5",
        "/usr/local/lib/libvlc.dylib"  # macOS
    ]
    
    for vlc_path in vlc_paths:
        if os.path.exists(vlc_path):
            arch = "32位" if "(x86)" in vlc_path else "64位"
            return {
                "status": "已安装",
                "path": vlc_path,
                "architecture": arch
            }
    
    return {
        "status": "未找到",
        "path": None,
        "architecture": None
    }


def check_ffmpeg_installation() -> Dict[str, Optional[str]]:
    """检查FFmpeg安装情况"""
    try:
        result = subprocess.run(
            ['ffmpeg', '-version'], 
            capture_output=True, 
            text=True, 
            timeout=10
        )
        if result.returncode == 0:
            version_line = result.stdout.split('\n')[0]
            return {
                "status": "已安装",
                "version": version_line,
                "path": subprocess.run(['where', 'ffmpeg'], capture_output=True, text=True).stdout.strip()
            }
    except (subprocess.TimeoutExpired, FileNotFoundError, subprocess.SubprocessError):
        pass
    
    return {
        "status": "未安装或不在PATH中",
        "version": None,
        "path": None
    }


def check_required_packages() -> List[Tuple[str, bool, Optional[str]]]:
    """检查必需的Python包"""
    required_packages = [
        ('PyQt5', 'PyQt5'),
        ('ffmpeg-python', 'ffmpeg'),
        ('whisper', 'whisper'),
        ('pysrt', 'pysrt'),
        ('requests', 'requests'),
        ('numpy', 'numpy'),
        ('pydub', 'pydub'),
        ('librosa', 'librosa'),
        ('psutil', 'psutil')
    ]
    
    results = []
    for display_name, import_name in required_packages:
        try:
            __import__(import_name)
            results.append((display_name, True, None))
        except ImportError as e:
            results.append((display_name, False, str(e)))
    
    return results


def generate_system_report() -> str:
    """生成完整的系统诊断报告"""
    report_lines = [
        "=" * 60,
        "VideoTranslator 系统诊断报告",
        "=" * 60,
        ""
    ]
    
    # Python环境信息
    python_info = check_python_environment()
    report_lines.extend([
        "📊 Python环境:",
        f"  版本: {python_info['python_version']}",
        f"  架构: {python_info['python_bits']}",
        f"  平台: {python_info['platform']}",
        f"  可执行文件: {python_info['executable']}",
        ""
    ])
    
    # VLC检查
    vlc_info = check_vlc_installation()
    report_lines.extend([
        "🎬 VLC媒体播放器:",
        f"  状态: {vlc_info['status']}",
    ])
    if vlc_info['path']:
        report_lines.extend([
            f"  路径: {vlc_info['path']}",
            f"  架构: {vlc_info['architecture']}",
        ])
    report_lines.append("")
    
    # FFmpeg检查
    ffmpeg_info = check_ffmpeg_installation()
    report_lines.extend([
        "🎞️ FFmpeg:",
        f"  状态: {ffmpeg_info['status']}",
    ])
    if ffmpeg_info['version']:
        report_lines.extend([
            f"  版本: {ffmpeg_info['version']}",
            f"  路径: {ffmpeg_info['path']}",
        ])
    report_lines.append("")
    
    # Python包检查
    package_results = check_required_packages()
    report_lines.extend([
        "📦 Python依赖包:",
    ])
    
    for package, installed, error in package_results:
        status = "✅ 已安装" if installed else "❌ 未安装"
        report_lines.append(f"  {package}: {status}")
        if error:
            report_lines.append(f"    错误: {error}")
    
    report_lines.extend([
        "",
        "=" * 60,
        f"报告生成时间: {platform.uname().node} - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "=" * 60
    ])
    
    return "\n".join(report_lines)


def main():
    """主函数"""
    print(generate_system_report())
    
    # 检查关键问题
    vlc_info = check_vlc_installation()
    ffmpeg_info = check_ffmpeg_installation()
    
    issues = []
    if vlc_info['status'] == '未找到':
        issues.append("⚠️  VLC未安装，字幕编辑功能可能不可用")
    
    if ffmpeg_info['status'] != '已安装':
        issues.append("⚠️  FFmpeg未安装，视频处理功能将不可用")
    
    package_results = check_required_packages()
    missing_packages = [pkg for pkg, installed, _ in package_results if not installed]
    if missing_packages:
        issues.append(f"⚠️  缺少Python包: {', '.join(missing_packages)}")
    
    if issues:
        print("\n🚨 发现问题:")
        for issue in issues:
            print(f"  {issue}")
        print("\n💡 建议运行: pip install -r requirements.txt")
    else:
        print("\n✅ 系统环境检查通过!")


if __name__ == "__main__":
    main()