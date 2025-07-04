#!/usr/bin/env python3
"""
强制重新导入配置模块的测试
"""

import sys
import importlib

def force_reload_test():
    print("=== 强制重新导入配置模块 ===")
    
    # 删除已导入的模块
    if 'app.config' in sys.modules:
        del sys.modules['app.config']
        print("删除了缓存的 app.config 模块")
    
    # 重新导入
    import app.config
    from app.config import AppConfig, get_config_manager
    
    print("重新导入完成")
    
    # 测试AppConfig实例
    print("1. 测试直接创建AppConfig实例:")
    config = AppConfig()
    print(f"   类型: {type(config)}")
    print(f"   有get方法: {hasattr(config, 'get')}")
    
    if hasattr(config, 'get'):
        print(f"   测试get方法: {config.get('whisper_model', 'default')}")
    else:
        print(f"   所有属性: {[attr for attr in dir(config) if not attr.startswith('_')]}")
    
    # 检查类定义
    import inspect
    print("\n2. AppConfig类定义信息:")
    print(f"   类名: {config.__class__.__name__}")
    print(f"   模块: {config.__class__.__module__}")
    print(f"   文件: {inspect.getfile(config.__class__)}")
    
    # 查看类的基类
    print(f"   基类: {config.__class__.__bases__}")
    
    # 查看类的__dict__
    print(f"   类__dict__键: {list(config.__class__.__dict__.keys())}")

if __name__ == "__main__":
    force_reload_test()
