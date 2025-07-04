#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def test_appconfig_dict_interface():
    """测试 AppConfig 的字典式接口"""
    print("测试 AppConfig 字典式接口...")
    
    try:
        from app.config import AppConfig
        
        config = AppConfig()
        
        print("1. 测试基本字典操作:")
        
        # 测试 get 方法
        whisper_model = config.get('whisper_model', 'base')
        print(f"✓ get() 方法: whisper_model = {whisper_model}")
        
        # 测试方括号访问
        provider = config['translation_provider']
        print(f"✓ __getitem__: translation_provider = {provider}")
        
        # 测试方括号赋值
        config['test_key'] = 'test_value'
        print(f"✓ __setitem__: 设置 test_key = {config['test_key']}")
        
        # 测试 in 操作符
        if 'whisper_model' in config:
            print("✓ __contains__: 'whisper_model' 存在于配置中")
        
        print("\n2. 测试新增的 setdefault 方法:")
        
        # 测试 setdefault - 键不存在的情况
        api_keys = config.setdefault('api_keys', {})
        print(f"✓ setdefault (新键): api_keys = {api_keys}")
        print(f"  类型: {type(api_keys)}")
        
        # 测试 setdefault - 键已存在的情况
        existing_model = config.setdefault('whisper_model', 'fallback')
        print(f"✓ setdefault (已存在): whisper_model = {existing_model}")
        
        print("\n3. 测试 API 密钥设置（模拟设置对话框逻辑）:")
        
        # 模拟设置对话框中的逻辑
        prov = 'openai'
        key = 'test-api-key-12345'
        
        # 这是原来失败的代码行
        config.setdefault('api_keys', {})[prov] = key
        print(f"✓ API 密钥设置成功: {config['api_keys']}")
        
        # 验证设置是否正确
        stored_key = config['api_keys'].get(prov)
        if stored_key == key:
            print(f"✓ API 密钥验证通过: {stored_key}")
        else:
            print(f"✗ API 密钥验证失败: 期望 {key}, 实际 {stored_key}")
            return False
        
        print("\n4. 测试多个 API 密钥:")
        
        providers_keys = {
            'deepl': 'deepl-key-67890',
            'google': 'google-key-abcde'
        }
        
        for provider, api_key in providers_keys.items():
            config.setdefault('api_keys', {})[provider] = api_key
        
        print(f"✓ 多个 API 密钥设置完成: {config['api_keys']}")
        
        # 验证所有密钥
        for provider, expected_key in providers_keys.items():
            actual_key = config['api_keys'].get(provider)
            if actual_key == expected_key:
                print(f"✓ {provider} 密钥正确: {actual_key}")
            else:
                print(f"✗ {provider} 密钥错误: 期望 {expected_key}, 实际 {actual_key}")
                return False
        
        return True
        
    except Exception as e:
        print(f"✗ AppConfig 字典接口测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_settings_dialog_simulation():
    """模拟设置对话框的操作"""
    print("\n模拟设置对话框操作...")
    
    try:
        from app.config import AppConfig
        
        # 模拟设置对话框的 accept 方法
        config = AppConfig()
        
        print("1. 模拟用户设置:")
        
        # 设置 Whisper 模型
        config['whisper_model'] = 'medium'
        print(f"✓ 设置 Whisper 模型: {config['whisper_model']}")
        
        # 设置翻译提供商
        prov = 'deepl'
        config['translation_provider'] = prov
        print(f"✓ 设置翻译提供商: {config['translation_provider']}")
        
        # 设置 API 密钥（这是原来失败的操作）
        key = 'user-entered-api-key-xyz789'
        config.setdefault('api_keys', {})[prov] = key
        print(f"✓ 设置 API 密钥: {config['api_keys'][prov]}")
        
        print("\n2. 验证配置状态:")
        
        # 检查所有设置是否正确
        assert config['whisper_model'] == 'medium'
        assert config['translation_provider'] == 'deepl'
        assert config['api_keys']['deepl'] == 'user-entered-api-key-xyz789'
        
        print("✓ 所有设置验证通过")
        
        print("\n3. 测试配置持久化准备:")
        
        # 测试 to_dict 方法（用于保存配置）
        config_dict = config.to_dict()
        print(f"✓ 配置转换为字典: {len(config_dict)} 个配置项")
        
        # 验证关键配置项在字典中
        key_items = ['whisper_model', 'translation_provider', 'api_keys']
        for item in key_items:
            if item in config_dict:
                print(f"✓ {item} 存在于配置字典中")
            else:
                print(f"✗ {item} 缺失于配置字典中")
                return False
        
        return True
        
    except Exception as e:
        print(f"✗ 设置对话框模拟测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_edge_cases():
    """测试边界情况"""
    print("\n测试边界情况...")
    
    try:
        from app.config import AppConfig
        
        config = AppConfig()
        
        print("1. 测试空 API 密钥字典:")
        
        # 第一次访问应该创建空字典
        api_keys = config.setdefault('api_keys', {})
        assert isinstance(api_keys, dict)
        print("✓ 空 API 密钥字典创建成功")
        
        print("\n2. 测试覆盖已存在的 API 密钥:")
        
        # 设置初始密钥
        config['api_keys']['test_provider'] = 'old_key'
        
        # 覆盖密钥
        config.setdefault('api_keys', {})['test_provider'] = 'new_key'
        
        if config['api_keys']['test_provider'] == 'new_key':
            print("✓ API 密钥覆盖成功")
        else:
            print("✗ API 密钥覆盖失败")
            return False
        
        print("\n3. 测试不存在的配置项:")
        
        # 测试不存在的键
        default_value = config.get('non_existent_key', 'default')
        if default_value == 'default':
            print("✓ 不存在的配置项返回默认值")
        else:
            print("✗ 不存在的配置项处理失败")
            return False
        
        return True
        
    except Exception as e:
        print(f"✗ 边界情况测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """主测试函数"""
    print("AppConfig setdefault 方法修复验证\n")
    
    results = []
    
    print("=" * 60)
    results.append(test_appconfig_dict_interface())
    
    print("=" * 60)
    results.append(test_settings_dialog_simulation())
    
    print("=" * 60)
    results.append(test_edge_cases())
    
    print("=" * 60)
    if all(results):
        print("✓ 所有测试通过！设置对话框的 API 密钥保存功能现在应该正常工作了。")
        print("\n修复内容:")
        print("• 在 AppConfig 类中添加了 setdefault() 方法")
        print("• 增强了字典式接口，新增 keys() 和 items() 方法")
        print("• 保持了与现有代码的完全兼容性")
        print("• 支持链式操作：config.setdefault('api_keys', {})[provider] = key")
        print("\n现在用户可以在设置对话框中正常保存 API 密钥了。")
    else:
        print("✗ 部分测试失败，请检查问题。")

if __name__ == "__main__":
    main()
