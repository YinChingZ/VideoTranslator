#!/usr/bin/env python3
"""
验证文件整理结果的脚本
"""

import os
import glob
from pathlib import Path

def check_directory_structure():
    """检查目录结构是否正确"""
    base_path = Path("d:/Projects/VideoTranslator")
    
    # 检查新创建的目录
    directories = [
        "tests",
        "tests/unit", 
        "tests/integration",
        "tests/debug",
        "docs",
        "docs/fix-reports",
        "docs/analysis",
        "scripts"
    ]
    
    print("=== 检查目录结构 ===")
    for dir_path in directories:
        full_path = base_path / dir_path
        if full_path.exists():
            print(f"✓ {dir_path} - 存在")
        else:
            print(f"✗ {dir_path} - 不存在")
    
    print("\n=== 检查测试文件分布 ===")
    
    # 检查单元测试
    unit_tests = list((base_path / "tests/unit").glob("test_*.py"))
    print(f"单元测试文件数量: {len(unit_tests)}")
    for test in unit_tests[:5]:  # 显示前5个
        print(f"  - {test.name}")
    if len(unit_tests) > 5:
        print(f"  ... 还有 {len(unit_tests) - 5} 个文件")
    
    # 检查集成测试
    integration_tests = list((base_path / "tests/integration").glob("*.py"))
    print(f"\n集成测试文件数量: {len(integration_tests)}")
    for test in integration_tests:
        print(f"  - {test.name}")
    
    # 检查调试脚本
    debug_scripts = list((base_path / "tests/debug").glob("*.py"))
    print(f"\n调试脚本文件数量: {len(debug_scripts)}")
    for script in debug_scripts:
        print(f"  - {script.name}")
    
    print("\n=== 检查文档分布 ===")
    
    # 检查修复报告
    fix_reports = list((base_path / "docs/fix-reports").glob("*.md"))
    print(f"修复报告数量: {len(fix_reports)}")
    for report in fix_reports:
        print(f"  - {report.name}")
    
    # 检查分析报告
    analysis_reports = list((base_path / "docs/analysis").glob("*"))
    print(f"\n分析报告数量: {len(analysis_reports)}")
    for report in analysis_reports:
        print(f"  - {report.name}")
    
    # 检查日志文件
    log_files = list((base_path / "logs").glob("*.log"))
    print(f"\n日志文件数量: {len(log_files)}")
    for log in log_files:
        print(f"  - {log.name}")
    
    print("\n=== 检查根目录清理情况 ===")
    
    # 检查根目录是否还有测试文件
    root_test_files = list(base_path.glob("test_*.py"))
    if root_test_files:
        print(f"⚠️  根目录仍有测试文件: {len(root_test_files)}")
        for f in root_test_files:
            print(f"  - {f.name}")
    else:
        print("✓ 根目录已清理完成，无测试文件")
    
    # 检查根目录是否还有报告文件
    root_report_files = list(base_path.glob("*_REPORT.md")) + list(base_path.glob("*_SUMMARY.md"))
    if root_report_files:
        print(f"⚠️  根目录仍有报告文件: {len(root_report_files)}")
        for f in root_report_files:
            print(f"  - {f.name}")
    else:
        print("✓ 根目录已清理完成，无报告文件")

if __name__ == "__main__":
    check_directory_structure()
