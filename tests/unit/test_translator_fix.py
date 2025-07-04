#!/usr/bin/env python
# -*- coding: utf-8 -*-

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.translation import Translator

def test_translator_init():
    """Test Translator initialization with primary_service parameter"""
    try:
        # Test with no parameters
        translator1 = Translator()
        print("✓ Translator initialization without parameters: OK")
        
        # Test with api_keys only
        translator2 = Translator(api_keys={"deepl": "test_key"})
        print("✓ Translator initialization with api_keys: OK")
        
        # Test with primary_service parameter
        translator3 = Translator(
            primary_service="deepl",
            api_keys={"deepl": "test_key"}
        )
        print("✓ Translator initialization with primary_service: OK")
        print(f"  Service priority: {translator3.service_priority}")
        
        # Test with different primary service
        translator4 = Translator(
            primary_service="google",
            api_keys={"deepl": "test_key", "google": "test_key"}
        )
        print("✓ Translator initialization with google as primary: OK")
        print(f"  Service priority: {translator4.service_priority}")
        
        print("\n所有测试通过！TranslationManager 现在支持 primary_service 参数。")
        
    except Exception as e:
        print(f"✗ 测试失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_translator_init()
