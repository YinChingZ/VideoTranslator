#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def test_config_imports():
    """测试配置导入和类型"""
    print("测试配置文件导入和数据类型...")
    
    try:
        from app.config import WHISPER_MODELS, TRANSLATION_PROVIDERS
        
        print("1. 检查 WHISPER_MODELS:")
        print(f"  类型: {type(WHISPER_MODELS)}")
        print(f"  内容: {WHISPER_MODELS}")
        
        if isinstance(WHISPER_MODELS, list):
            print("✓ WHISPER_MODELS 是列表类型（正确）")
            if len(WHISPER_MODELS) > 0:
                print(f"✓ WHISPER_MODELS 包含 {len(WHISPER_MODELS)} 个模型")
            else:
                print("✗ WHISPER_MODELS 为空")
                return False
        else:
            print(f"✗ WHISPER_MODELS 类型错误: {type(WHISPER_MODELS)}")
            return False
        
        print("\n2. 检查 TRANSLATION_PROVIDERS:")
        print(f"  类型: {type(TRANSLATION_PROVIDERS)}")
        print(f"  内容: {TRANSLATION_PROVIDERS}")
        
        if isinstance(TRANSLATION_PROVIDERS, list):
            print("✓ TRANSLATION_PROVIDERS 是列表类型（正确）")
            if len(TRANSLATION_PROVIDERS) > 0:
                print(f"✓ TRANSLATION_PROVIDERS 包含 {len(TRANSLATION_PROVIDERS)} 个提供商")
            else:
                print("✗ TRANSLATION_PROVIDERS 为空")
                return False
        else:
            print(f"✗ TRANSLATION_PROVIDERS 类型错误: {type(TRANSLATION_PROVIDERS)}")
            return False
        
        return True
        
    except Exception as e:
        print(f"✗ 配置导入测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_main_window_compatibility():
    """测试主窗口设置对话框的兼容性"""
    print("\n测试主窗口设置对话框兼容性...")
    
    try:
        from app.config import WHISPER_MODELS, TRANSLATION_PROVIDERS
        
        print("1. 模拟 Whisper 模型下拉框填充:")
        models_list = []
        for model in WHISPER_MODELS:  # 使用修复后的方式
            models_list.append(model)
        
        print(f"✓ 成功遍历 WHISPER_MODELS: {models_list}")
        
        print("\n2. 模拟翻译提供商下拉框填充:")
        providers_list = []
        for prov in TRANSLATION_PROVIDERS:
            providers_list.append(prov)
        
        print(f"✓ 成功遍历 TRANSLATION_PROVIDERS: {providers_list}")
        
        print("\n3. 测试默认值设置:")
        default_model = 'base'
        default_provider = 'openai'
        
        if default_model in WHISPER_MODELS:
            print(f"✓ 默认 Whisper 模型 '{default_model}' 存在于选项中")
        else:
            print(f"✗ 默认 Whisper 模型 '{default_model}' 不在选项中")
            return False
        
        if default_provider in TRANSLATION_PROVIDERS:
            print(f"✓ 默认翻译提供商 '{default_provider}' 存在于选项中")
        else:
            print(f"✗ 默认翻译提供商 '{default_provider}' 不在选项中")
            return False
        
        return True
        
    except Exception as e:
        print(f"✗ 主窗口兼容性测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_config_manager_integration():
    """测试配置管理器集成"""
    print("\n测试配置管理器集成...")
    
    try:
        from app.config import AppConfig
        from app.config import WHISPER_MODELS, TRANSLATION_PROVIDERS
        
        # 模拟配置字典
        test_config = {
            'whisper_model': 'medium',
            'translation_provider': 'deepl'
        }
        
        print("1. 测试配置读取:")
        whisper_model = test_config.get('whisper_model', 'base')
        translation_provider = test_config.get('translation_provider', 'openai')
        
        print(f"  Whisper 模型: {whisper_model}")
        print(f"  翻译提供商: {translation_provider}")
        
        print("\n2. 验证配置值有效性:")
        if whisper_model in WHISPER_MODELS:
            print(f"✓ Whisper 模型 '{whisper_model}' 有效")
        else:
            print(f"✗ Whisper 模型 '{whisper_model}' 无效")
            return False
        
        if translation_provider in TRANSLATION_PROVIDERS:
            print(f"✓ 翻译提供商 '{translation_provider}' 有效")
        else:
            print(f"✗ 翻译提供商 '{translation_provider}' 无效")
            return False
        
        return True
        
    except Exception as e:
        print(f"✗ 配置管理器集成测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """主测试函数"""
    print("设置对话框修复验证\n")
    
    results = []
    
    print("=" * 60)
    results.append(test_config_imports())
    
    print("=" * 60)
    results.append(test_main_window_compatibility())
    
    print("=" * 60)
    results.append(test_config_manager_integration())
    
    print("=" * 60)
    if all(results):
        print("✓ 所有测试通过！设置对话框现在应该可以正常工作了。")
        print("\n修复内容:")
        print("• 修正了 WHISPER_MODELS 的使用方式")
        print("• 将 '.keys()' 方法调用改为直接遍历列表")
        print("• 保持了与现有配置结构的兼容性")
        print("• 验证了默认值的有效性")
        print("\n现在设置对话框应该可以正常打开并显示可用选项。")
    else:
        print("✗ 部分测试失败，请检查问题。")

if __name__ == "__main__":
    main()
