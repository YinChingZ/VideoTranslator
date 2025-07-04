#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import os
import json
import tempfile
from pathlib import Path

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.utils.checkpoint import CheckpointManager, serialize_for_json

def create_corrupted_checkpoint_file(checkpoint_dir):
    """创建一个损坏的检查点文件用于测试"""
    corrupted_file = Path(checkpoint_dir) / "corrupted_checkpoint.json"
    
    # 写入无效的JSON
    with open(corrupted_file, 'w', encoding='utf-8') as f:
        f.write('{"valid": "data", "invalid": ')  # 故意不完成JSON
    
    return corrupted_file

def test_checkpoint_resilience():
    """测试检查点系统的错误恢复能力"""
    print("测试检查点系统错误恢复能力...\n")
    
    with tempfile.TemporaryDirectory() as temp_dir:
        try:
            # 创建损坏的检查点文件
            corrupted_file = create_corrupted_checkpoint_file(temp_dir)
            print(f"✓ 创建损坏的检查点文件: {corrupted_file}")
            
            # 初始化检查点管理器（应该自动清理损坏文件）
            manager = CheckpointManager(temp_dir)
            print("✓ CheckpointManager 初始化成功，自动清理了损坏文件")
            
            # 检查损坏文件是否被清理
            if not corrupted_file.exists():
                print("✓ 损坏的检查点文件已被自动清理")
            else:
                print("✗ 损坏的检查点文件未被清理")
                return False
            
            # 测试正常的检查点保存和加载
            test_video_path = "test_video.mp4"
            test_stage_data = {
                'audio_path': Path('/test/audio.wav'),
                'duration': 120.5,
                'sample_rate': 16000
            }
            
            # 保存检查点
            success = manager.save_checkpoint(
                video_path=test_video_path,
                stage="audio_extraction",
                stage_data=test_stage_data,
                source_language="en",
                target_language="zh-CN"
            )
            
            if success:
                print("✓ 检查点保存成功")
            else:
                print("✗ 检查点保存失败")
                return False
            
            # 加载检查点
            loaded_checkpoint = manager.load_checkpoint(test_video_path)
            if loaded_checkpoint:
                print("✓ 检查点加载成功")
                print(f"  完成阶段: {loaded_checkpoint.completed_stages}")
                return True
            else:
                print("✗ 检查点加载失败")
                return False
                
        except Exception as e:
            print(f"✗ 测试失败: {e}")
            import traceback
            traceback.print_exc()
            return False

def test_json_serialization():
    """测试JSON序列化功能"""
    print("测试JSON序列化功能...\n")
    
    try:
        # 测试复杂数据结构的序列化
        complex_data = {
            'paths': [Path('/path1'), Path('/path2')],
            'nested': {
                'path': Path('/nested/path'),
                'data': {'more_paths': Path('/more/path')}
            },
            'mixed_list': [Path('/list/path'), 'string', 123, {'inner_path': Path('/inner')}]
        }
        
        serialized = serialize_for_json(complex_data)
        print("✓ 复杂数据结构序列化成功")
        
        # 验证所有Path对象都被转换
        def check_no_paths(obj):
            if isinstance(obj, Path):
                return False
            elif isinstance(obj, dict):
                return all(check_no_paths(v) for v in obj.values())
            elif isinstance(obj, list):
                return all(check_no_paths(item) for item in obj)
            return True
        
        if check_no_paths(serialized):
            print("✓ 所有Path对象都已正确转换为字符串")
        else:
            print("✗ 仍然存在未转换的Path对象")
            return False
        
        # 测试JSON序列化
        json_str = json.dumps(serialized, ensure_ascii=False, indent=2)
        print("✓ JSON序列化成功")
        
        # 测试反序列化
        deserialized = json.loads(json_str)
        print("✓ JSON反序列化成功")
        
        return True
        
    except Exception as e:
        print(f"✗ JSON序列化测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    print("检查点系统修复验证\n")
    
    print("=" * 50)
    test1_result = test_json_serialization()
    
    print("\n" + "=" * 50)
    test2_result = test_checkpoint_resilience()
    
    print("\n" + "=" * 50)
    if test1_result and test2_result:
        print("✓ 所有测试通过！检查点系统修复成功。")
    else:
        print("✗ 部分测试失败。")

if __name__ == "__main__":
    main()
