#!/usr/bin/env python3
"""
彻底测试配置文件的get方法
"""

print("=== 新的Python进程测试 ===")

# 直接导入并测试
from app.config import AppConfig, get_config_manager

# 创建配置实例
config = AppConfig()
print(f"配置类型: {type(config)}")
print(f"配置类: {config.__class__}")
print(f"配置模块: {config.__class__.__module__}")

# 检查所有方法
methods = [method for method in dir(config) if not method.startswith('_')]
print(f"所有方法: {methods}")

# 专门检查get方法
has_get = hasattr(config, 'get')
print(f"有get方法: {has_get}")

if has_get:
    try:
        result = config.get('whisper_model', 'default_value')
        print(f"get方法测试成功: {result}")
    except Exception as e:
        print(f"get方法测试失败: {e}")
else:
    print("get方法不存在")

# 测试ConfigManager
manager = get_config_manager()
manager_config = manager.config
print(f"管理器配置类型: {type(manager_config)}")
print(f"管理器配置有get方法: {hasattr(manager_config, 'get')}")

# 测试语言代码访问（这是原始错误的来源）
try:
    language_codes = config.get("language_codes", {})
    print(f"language_codes测试成功: {type(language_codes)}, 长度: {len(language_codes)}")
except Exception as e:
    print(f"language_codes测试失败: {e}")

print("=== 测试完成 ===")
