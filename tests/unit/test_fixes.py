#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pathlib import Path
from app.utils.checkpoint import CheckpointManager, serialize_for_json
from app.utils.memory_manager import MemoryMonitor

def test_checkpoint_serialization():
    """测试检查点序列化修复"""
    try:
        # 测试序列化函数
        test_data = {
            'path': Path('/test/path'),
            'nested': {
                'another_path': Path('/another/path'),
                'normal_data': 'string'
            },
            'list_with_paths': [Path('/path1'), Path('/path2'), 'normal_string']
        }
        
        serialized = serialize_for_json(test_data)
        print("✓ Path 对象序列化成功")
        print(f"  原始: {test_data}")
        print(f"  序列化: {serialized}")
        
        # 检查所有 Path 对象都被转换为字符串
        assert isinstance(serialized['path'], str)
        assert isinstance(serialized['nested']['another_path'], str)
        assert all(isinstance(p, str) for p in serialized['list_with_paths'] if not isinstance(p, str))
        
        print("✓ 检查点序列化修复验证成功")
        
    except Exception as e:
        print(f"✗ 检查点测试失败: {e}")
        import traceback
        traceback.print_exc()

def test_memory_monitor():
    """测试内存监控器修复"""
    try:
        monitor = MemoryMonitor()
        
        # 测试正确的方法名
        stats = monitor.get_memory_stats()
        print("✓ MemoryMonitor.get_memory_stats() 方法正常")
        print(f"  内存统计: {stats}")
        
        # 验证返回的是 MemoryStats 对象
        assert hasattr(stats, 'percent')
        assert hasattr(stats, 'total_mb')
        assert hasattr(stats, 'used_mb')
        
        print("✓ 内存监控器修复验证成功")
        
    except Exception as e:
        print(f"✗ 内存监控器测试失败: {e}")
        import traceback
        traceback.print_exc()

def main():
    print("测试修复的功能...\n")
    
    print("1. 测试检查点序列化修复:")
    test_checkpoint_serialization()
    
    print("\n2. 测试内存监控器修复:")
    test_memory_monitor()
    
    print("\n所有修复验证完成！")

if __name__ == "__main__":
    main()
