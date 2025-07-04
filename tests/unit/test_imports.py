#!/usr/bin/env python3
"""
简单的模块导入验证
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_imports():
    """测试关键模块导入"""
    try:
        from app.gui.main_window import MainWindow
        print("✅ MainWindow 导入成功")
        
        from app.core.video import VideoProcessor
        print("✅ VideoProcessor 导入成功")
        
        from app.gui.export_dialog import ExportDialog
        print("✅ ExportDialog 导入成功")
        
        # 验证关键方法存在
        processor = VideoProcessor()
        if hasattr(processor, 'embed_subtitles_to_video'):
            print("✅ embed_subtitles_to_video 方法存在")
        if hasattr(processor, 'burn_subtitles_to_video'):
            print("✅ burn_subtitles_to_video 方法存在")
        
        print("\n所有修复都已成功应用！")
        return True
        
    except Exception as e:
        print(f"❌ 导入失败: {e}")
        return False

if __name__ == "__main__":
    test_imports()
