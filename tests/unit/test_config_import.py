#!/usr/bin/env python3
# 测试config模块导入

import sys
import os

# 添加项目根目录到路径
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

print("正在测试config模块导入...")

try:
    # 尝试导入整个模块
    import app.config as config_module
    print(f"模块导入成功，属性: {dir(config_module)}")
    
    # 检查是否存在get_config_manager
    if hasattr(config_module, 'get_config_manager'):
        print("get_config_manager 函数存在")
        try:
            config_manager = config_module.get_config_manager()
            print(f"配置管理器创建成功: {type(config_manager)}")
        except Exception as e:
            print(f"配置管理器创建失败: {e}")
    else:
        print("get_config_manager 函数不存在")
        
    # 检查类是否存在
    if hasattr(config_module, 'ConfigManager'):
        print("ConfigManager 类存在")
    else:
        print("ConfigManager 类不存在")
        
except Exception as e:
    print(f"导入失败: {e}")
    import traceback
    traceback.print_exc()
