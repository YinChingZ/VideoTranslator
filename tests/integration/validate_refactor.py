#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
重构验证脚本 - 验证核心功能是否正常工作
Refactoring Validation Script - Test core functionality after refactoring
"""

import sys
import os
import logging
from pathlib import Path

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_config_system():
    """测试配置系统"""
    print("🔧 测试配置系统...")
    try:
        from app.config import get_config_manager, AppConfig
        
        # 测试配置管理器
        config_manager = get_config_manager()
        config = config_manager.config
        
        assert isinstance(config, AppConfig), "配置对象类型错误"
        assert config.app_version == "1.0.0", "版本号不正确"
        assert config.temp_dir.exists(), "临时目录不存在"
        assert config.output_dir.exists(), "输出目录不存在"
        
        # 测试配置更新
        original_lang = config.default_target_language
        config_manager.update(default_target_language="fr")
        assert config_manager.config.default_target_language == "fr", "配置更新失败"
        
        # 恢复原设置
        config_manager.update(default_target_language=original_lang)
        
        print("  ✅ 配置系统正常")
        return True
        
    except Exception as e:
        print(f"  ❌ 配置系统错误: {e}")
        return False


def test_logger_system():
    """测试日志系统"""
    print("📝 测试日志系统...")
    try:
        from app.utils.logger import setup_logger, get_performance_logger, SensitiveInfoFilter
        
        # 设置测试日志
        logger = setup_logger(logging.DEBUG)
        
        # 测试性能日志
        perf_logger = get_performance_logger("test")
        perf_logger.start_timer("test_operation")
        import time
        time.sleep(0.1)  # 模拟操作
        elapsed = perf_logger.stop_timer("test_operation")
        
        assert elapsed > 0.05, "性能计时器工作异常"
        
        # 测试敏感信息过滤
        filter = SensitiveInfoFilter()
        test_text = "API key is sk-1234567890abcdef and token is Bearer xyz123"
        filtered = filter._redact_sensitive_info(test_text)
        
        assert "sk-1234567890abcdef" not in filtered, "敏感信息过滤失败"
        assert "xyz123" not in filtered, "敏感信息过滤失败"
        
        print("  ✅ 日志系统正常")
        return True
        
    except Exception as e:
        print(f"  ❌ 日志系统错误: {e}")
        return False


def test_translation_system():
    """测试翻译系统"""
    print("🌍 测试翻译系统...")
    try:
        from app.core.translation import TranslationCache, TranslationResult, TerminologyManager
        
        # 测试翻译缓存
        cache = TranslationCache()
        
        # 创建测试结果
        test_result = TranslationResult(
            original_text="Hello",
            translated_text="你好",
            source_lang="en",
            target_lang="zh-CN",
            confidence=0.95,
            service="test"
        )
        
        # 测试存储和检索
        cache.store(test_result)
        retrieved = cache.get("Hello", "en", "zh-CN", "test")
        
        assert retrieved is not None, "缓存检索失败"
        assert retrieved.translated_text == "你好", "缓存数据不正确"
        
        # 测试术语管理
        terminology = TerminologyManager()
        terminology.add_term("en", "zh-CN", "computer", "计算机")
        
        test_text = "This is a computer program"
        result_text = terminology.apply_terminology(test_text, "en", "zh-CN")
        assert "计算机" in result_text, "术语替换失败"
        
        print("  ✅ 翻译系统正常")
        return True
        
    except Exception as e:
        print(f"  ❌ 翻译系统错误: {e}")
        return False


def test_temp_file_system():
    """测试临时文件系统"""
    print("📁 测试临时文件系统...")
    try:
        from app.utils.temp_files import TempFileManager
        
        # 创建临时文件管理器
        temp_manager = TempFileManager()
        
        # 测试创建临时文件
        temp_file = temp_manager.create_temp_file(".txt")
        assert os.path.exists(os.path.dirname(temp_file)), "临时文件目录不存在"
        
        # 创建文件并写入内容
        with open(temp_file, 'w') as f:
            f.write("test content")
        
        assert os.path.exists(temp_file), "临时文件创建失败"
        
        # 测试创建临时目录
        temp_dir = temp_manager.create_temp_dir()
        assert os.path.exists(temp_dir), "临时目录创建失败"
        
        print("  ✅ 临时文件系统正常")
        return True
        
    except Exception as e:
        print(f"  ❌ 临时文件系统错误: {e}")
        return False


def test_import_compatibility():
    """测试导入兼容性"""
    print("📦 测试导入兼容性...")
    try:
        # 测试核心模块导入
        from app.core import audio, speech, subtitle, video
        from app.gui import main_window, processing, subtitle_editor
        from app.utils import format_converter, logger, temp_files
        from app.resources import icons, styles
        
        print("  ✅ 所有模块导入正常")
        return True
        
    except Exception as e:
        print(f"  ❌ 模块导入错误: {e}")
        return False


def main():
    """主测试函数"""
    print("=" * 60)
    print("VideoTranslator 重构验证")
    print("=" * 60)
    print()
    
    tests = [
        test_config_system,
        test_logger_system,
        test_translation_system,
        test_temp_file_system,
        test_import_compatibility
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        try:
            if test():
                passed += 1
        except Exception as e:
            print(f"  ❌ 测试异常: {e}")
    
    print()
    print("=" * 60)
    print(f"测试结果: {passed}/{total} 通过")
    
    if passed == total:
        print("🎉 所有测试通过！重构成功！")
        print()
        print("下一步建议:")
        print("1. 运行主程序测试GUI功能: python main.py")
        print("2. 测试视频导入和处理功能")
        print("3. 验证翻译API配置和功能")
        return 0
    else:
        print("⚠️  部分测试失败，需要进一步检查")
        return 1


if __name__ == "__main__":
    sys.exit(main())
