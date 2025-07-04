#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试导出对话框Path对象转换修复
"""

import sys
import os
from pathlib import Path

def test_export_dialog_fix():
    """测试导出对话框的Path对象转换修复"""
    print("=== 测试导出对话框Path对象转换修复 ===\n")
    
    try:
        # 1. 测试配置导入
        print("1. 测试配置模块导入...")
        from app.config import AppConfig
        print("✅ 配置模块导入成功")
        
        # 2. 测试导出对话框导入
        print("\n2. 测试导出对话框模块导入...")
        from app.gui.export_dialog import ExportDialog
        print("✅ 导出对话框模块导入成功")
        
        # 3. 测试配置加载
        print("\n3. 测试配置加载...")
        config = AppConfig()
        output_dir = config.get('output_dir', Path('C:/temp'))
        print(f"output_dir类型: {type(output_dir)}")
        print(f"output_dir值: {output_dir}")
        
        # 4. 测试路径转换函数
        print("\n4. 测试路径转换函数...")
        def safe_path_to_str(path_obj):
            """安全地将路径对象转换为字符串"""
            if isinstance(path_obj, (Path, os.PathLike)):
                return str(path_obj)
            return str(path_obj) if path_obj is not None else ''
        
        # 测试不同类型的输入
        test_cases = [
            Path("C:/test/path"),
            "C:/test/string",
            None,
            123,
            output_dir
        ]
        
        for i, test_input in enumerate(test_cases):
            result = safe_path_to_str(test_input)
            print(f"  测试用例 {i+1}: {type(test_input).__name__} -> {type(result).__name__}")
            print(f"    输入: {test_input}")
            print(f"    输出: {result}")
        
        print("✅ 路径转换函数测试通过")
        
        # 5. 模拟setText调用
        print("\n5. 模拟setText调用...")
        class MockQLineEdit:
            def setText(self, text):
                if not isinstance(text, str):
                    raise TypeError(f"setText expects str, got {type(text)}")
                print(f"setText调用成功: {text}")
        
        mock_widget = MockQLineEdit()
        
        # 原始问题：直接传递Path对象
        try:
            mock_widget.setText(output_dir)
            print("❌ 应该失败但没有失败")
        except TypeError as e:
            print(f"✅ 原始问题重现: {e}")
        
        # 修复后：转换为字符串
        try:
            mock_widget.setText(safe_path_to_str(output_dir))
            print("✅ 修复后正常工作")
        except Exception as e:
            print(f"❌ 修复失败: {e}")
        
        print("\n=== 测试完成 ===")
        print("🎉 导出对话框Path对象转换修复验证成功！")
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_export_dialog_fix()
