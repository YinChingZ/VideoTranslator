#!/usr/bin/env python3
"""
临时测试配置系统
"""

def test_config():
    print("=== 配置系统测试 ===")
    
    # 直接导入AppConfig类
    from app.config import AppConfig, get_config_manager
    import inspect
    
    # 测试直接创建AppConfig实例
    print("1. 直接创建AppConfig实例:")
    config_direct = AppConfig()
    print(f"   类型: {type(config_direct)}")
    print(f"   有get方法: {hasattr(config_direct, 'get')}")
    
    # 测试通过ConfigManager获取配置
    print("\n2. 通过ConfigManager获取配置:")
    manager = get_config_manager()
    config_from_manager = manager.config
    print(f"   类型: {type(config_from_manager)}")
    print(f"   有get方法: {hasattr(config_from_manager, 'get')}")
    
    # 检查类的源代码
    print("\n3. AppConfig类源代码摘要:")
    source = inspect.getsource(AppConfig)
    lines = source.split('\n')
    for i, line in enumerate(lines[:20]):  # 只显示前20行
        print(f"   {i+1:2d}: {line}")
    
    # 测试get方法
    if hasattr(config_direct, 'get'):
        print("\n4. 测试get方法:")
        print(f"   whisper_model: {config_direct.get('whisper_model', 'default')}")
        print(f"   不存在的键: {config_direct.get('nonexistent', 'default_value')}")
    else:
        print("\n4. get方法不存在，列出所有属性:")
        attrs = [attr for attr in dir(config_direct) if not attr.startswith('_')]
        print(f"   属性: {attrs}")

if __name__ == "__main__":
    test_config()
