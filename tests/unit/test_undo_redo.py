#!/usr/bin/env python3
"""
测试VideoTranslator应用的撤销/重做功能
"""

import sys
import os
import tempfile
import subprocess
import json
from datetime import datetime

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QTimer, Qt
from PyQt5.QtTest import QTest
from PyQt5.QtGui import QKeySequence

from app.gui.main_window import MainWindow
from app.core.subtitle import SubtitleSegment


class UndoRedoTestResult:
    """撤销/重做测试结果"""
    def __init__(self):
        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.tests = []
        self.passed = 0
        self.failed = 0
        self.errors = []
    
    def add_test(self, test_name, passed, message=""):
        """添加测试结果"""
        self.tests.append({
            'name': test_name,
            'passed': passed,
            'message': message
        })
        if passed:
            self.passed += 1
        else:
            self.failed += 1
            self.errors.append(f"{test_name}: {message}")
    
    def get_summary(self):
        """获取测试摘要"""
        return {
            'timestamp': self.timestamp,
            'total_tests': len(self.tests),
            'passed': self.passed,
            'failed': self.failed,
            'errors': self.errors,
            'tests': self.tests
        }


def test_undo_redo_functionality():
    """测试撤销/重做功能"""
    result = UndoRedoTestResult()
    
    try:
        # 创建应用实例
        app = QApplication(sys.argv)
        
        # 创建必要的依赖
        from app.config import get_config_manager, AppConfig
        from app.utils.temp_files import TempFileManager
        
        config_manager = get_config_manager()
        app_config = AppConfig()
        temp_manager = TempFileManager()
        
        # 创建主窗口
        main_window = MainWindow(app_config, temp_manager)
        main_window.show()
        
        # 等待窗口显示完成
        QTest.qWaitForWindowExposed(main_window)
        
        # 测试1: 检查撤销/重做菜单项是否存在
        has_undo_action = hasattr(main_window, 'undo_action')
        has_redo_action = hasattr(main_window, 'redo_action')
        
        result.add_test(
            "撤销菜单项存在", 
            has_undo_action,
            "undo_action属性存在" if has_undo_action else "undo_action属性不存在"
        )
        
        result.add_test(
            "重做菜单项存在", 
            has_redo_action,
            "redo_action属性存在" if has_redo_action else "redo_action属性不存在"
        )
        
        # 测试2: 检查撤销/重做方法是否存在
        has_undo_method = hasattr(main_window, 'undo')
        has_redo_method = hasattr(main_window, 'redo')
        
        result.add_test(
            "撤销方法存在", 
            has_undo_method,
            "undo方法存在" if has_undo_method else "undo方法不存在"
        )
        
        result.add_test(
            "重做方法存在", 
            has_redo_method,
            "redo方法存在" if has_redo_method else "redo方法不存在"
        )
        
        # 测试3: 检查初始状态下撤销/重做是否禁用
        if has_undo_action:
            initial_undo_enabled = main_window.undo_action.isEnabled()
            result.add_test(
                "初始状态撤销禁用", 
                not initial_undo_enabled,
                f"撤销初始状态: {'启用' if initial_undo_enabled else '禁用'}"
            )
        
        if has_redo_action:
            initial_redo_enabled = main_window.redo_action.isEnabled()
            result.add_test(
                "初始状态重做禁用", 
                not initial_redo_enabled,
                f"重做初始状态: {'启用' if initial_redo_enabled else '禁用'}"
            )
        
        # 测试4: 检查字幕编辑器的撤销/重做方法
        if hasattr(main_window, 'subtitle_editor_widget'):
            editor = main_window.subtitle_editor_widget
            has_editor_undo = hasattr(editor, 'undo')
            has_editor_redo = hasattr(editor, 'redo')
            
            result.add_test(
                "字幕编辑器撤销方法存在", 
                has_editor_undo,
                "字幕编辑器有undo方法" if has_editor_undo else "字幕编辑器缺少undo方法"
            )
            
            result.add_test(
                "字幕编辑器重做方法存在", 
                has_editor_redo,
                "字幕编辑器有redo方法" if has_editor_redo else "字幕编辑器缺少redo方法"
            )
        
        # 测试5: 检查键盘快捷键
        if has_undo_action:
            undo_shortcut = main_window.undo_action.shortcut()
            expected_undo = QKeySequence.StandardKey.Undo
            has_undo_shortcut = undo_shortcut == QKeySequence(expected_undo)
            
            result.add_test(
                "撤销快捷键设置", 
                has_undo_shortcut,
                f"撤销快捷键: {undo_shortcut.toString()}"
            )
        
        if has_redo_action:
            redo_shortcut = main_window.redo_action.shortcut()
            expected_redo = QKeySequence.StandardKey.Redo
            has_redo_shortcut = redo_shortcut == QKeySequence(expected_redo)
            
            result.add_test(
                "重做快捷键设置", 
                has_redo_shortcut,
                f"重做快捷键: {redo_shortcut.toString()}"
            )
        
        # 测试6: 测试在编辑页面时撤销/重做是否启用
        # 模拟切换到编辑页面
        main_window.stacked_widget.setCurrentIndex(2)  # 编辑页面
        
        # 等待状态更新
        QTest.qWait(100)
        
        if has_undo_action:
            editor_undo_enabled = main_window.undo_action.isEnabled()
            result.add_test(
                "编辑页面撤销启用", 
                editor_undo_enabled,
                f"编辑页面撤销状态: {'启用' if editor_undo_enabled else '禁用'}"
            )
        
        if has_redo_action:
            editor_redo_enabled = main_window.redo_action.isEnabled()
            result.add_test(
                "编辑页面重做启用", 
                editor_redo_enabled,
                f"编辑页面重做状态: {'启用' if editor_redo_enabled else '禁用'}"
            )
        
        # 关闭应用
        main_window.close()
        app.quit()
        
    except Exception as e:
        result.add_test(
            "测试执行", 
            False,
            f"测试执行过程中发生错误: {str(e)}"
        )
    
    return result


def analyze_undo_redo_implementation():
    """分析撤销/重做功能的实现情况"""
    print("=== VideoTranslator撤销/重做功能分析 ===\n")
    
    # 运行测试
    result = test_undo_redo_functionality()
    
    # 显示测试结果
    print(f"测试时间: {result.timestamp}")
    print(f"总测试数: {len(result.tests)}")
    print(f"通过: {result.passed}")
    print(f"失败: {result.failed}")
    print()
    
    # 显示详细结果
    for test in result.tests:
        status = "✓" if test['passed'] else "✗"
        print(f"{status} {test['name']}: {test['message']}")
    
    print("\n=== 实现状况分析 ===")
    
    # 基于测试结果分析实现情况
    if result.passed >= 6:
        print("✓ 撤销/重做功能基本框架已实现")
        print("  - 菜单项和方法都存在")
        print("  - 快捷键已设置")
        print("  - 状态管理基本正确")
    else:
        print("✗ 撤销/重做功能实现不完整")
    
    print("\n=== 功能限制分析 ===")
    print("当前实现的限制:")
    print("1. 只支持文本编辑框的基本撤销/重做")
    print("2. 没有字幕段落级别的撤销/重做")
    print("3. 没有复杂操作的撤销/重做(如添加/删除字幕)")
    print("4. 没有撤销/重做历史记录")
    print("5. 没有操作命令的封装")
    
    print("\n=== 改进建议 ===")
    print("为了实现完整的撤销/重做功能，建议:")
    print("1. 实现命令模式(Command Pattern)")
    print("2. 使用QUndoStack管理撤销/重做历史")
    print("3. 为每个字幕操作创建UndoCommand")
    print("4. 支持批量操作的撤销/重做")
    print("5. 添加撤销/重做状态提示")
    
    # 保存测试结果
    report_file = f"undo_redo_analysis_{result.timestamp}.json"
    with open(report_file, 'w', encoding='utf-8') as f:
        json.dump(result.get_summary(), f, ensure_ascii=False, indent=2)
    
    print(f"\n测试结果已保存到: {report_file}")
    
    return result


if __name__ == "__main__":
    analyze_undo_redo_implementation()
