#!/usr/bin/env python3
"""
测试GUI集成，确保processing.py中的Translator初始化不会出错
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_gui_translator_initialization():
    """测试GUI中的Translator初始化"""
    try:
        # 模拟GUI中的Translator初始化
        from app.core.translation import Translator
        
        # 这是processing.py中实际使用的参数
        translator = Translator(
            api_keys={'deepl': 'test_key'},
            primary_service='deepl'
        )
        
        print("✓ GUI集成测试通过：Translator可以正常初始化")
        print(f"  服务优先级: {translator.service_priority}")
        return True
        
    except Exception as e:
        print(f"✗ GUI集成测试失败: {e}")
        return False

if __name__ == "__main__":
    success = test_gui_translator_initialization()
    if success:
        print("\n🎉 修复成功！应用程序现在应该可以正常运行了。")
    else:
        print("\n❌ 还有问题需要解决。")
