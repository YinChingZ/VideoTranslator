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
    test_data = {
        'path': Path('/test/path'),
        'nested': {
            'another_path': Path('/another/path'),
            'normal_data': 'string'
        },
        'list_with_paths': [Path('/path1'), Path('/path2'), 'normal_string']
    }

    serialized = serialize_for_json(test_data)

    assert serialized == {
        'path': '/test/path',
        'nested': {
            'another_path': '/another/path',
            'normal_data': 'string',
        },
        'list_with_paths': ['/path1', '/path2', 'normal_string'],
    }

def test_memory_monitor():
    """测试内存监控器修复"""
    monitor = MemoryMonitor()
    stats = monitor.get_memory_stats()

    assert 0 <= stats.percent <= 100
    assert stats.total_mb > 0
    assert 0 <= stats.used_mb <= stats.total_mb

def main():
    print("测试修复的功能...\n")
    
    print("1. 测试检查点序列化修复:")
    test_checkpoint_serialization()
    
    print("\n2. 测试内存监控器修复:")
    test_memory_monitor()
    
    print("\n所有修复验证完成！")

if __name__ == "__main__":
    main()
