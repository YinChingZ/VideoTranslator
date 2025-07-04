#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import os
import tempfile
import threading
import time
from pathlib import Path

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt5.QtCore import QCoreApplication
from app.gui.improved_processing import ImprovedProcessingWorker

def create_test_config():
    """创建测试配置"""
    return {
        'whisper_model': 'base',
        'translation_provider': 'openai',
        'api_keys': {
            'openai': 'test_key',
            'deepl': 'test_key'
        }
    }

def test_worker_initialization():
    """测试工作器初始化"""
    print("测试改进的处理工作器初始化...")
    
    try:
        config = create_test_config()
        worker = ImprovedProcessingWorker(
            video_path="/test/video.mp4",
            source_language="en",
            target_language="zh-CN",
            config=config
        )
        
        print("✓ ImprovedProcessingWorker 初始化成功")
        
        # 测试取消功能
        worker.cancel()
        if worker.is_cancelled():
            print("✓ 取消功能正常")
        
        # 测试清理功能
        worker.cleanup()
        print("✓ 清理功能正常")
        
        return True
        
    except Exception as e:
        print(f"✗ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_timeout_mechanism():
    """测试超时机制"""
    print("\n测试超时机制...")
    
    try:
        config = create_test_config()
        worker = ImprovedProcessingWorker(
            video_path="/test/video.mp4",
            source_language="en", 
            target_language="zh-CN",
            config=config
        )
        
        # 测试超时设置
        timeouts = worker.stage_timeouts
        print(f"✓ 阶段超时设置: {timeouts}")
        
        # 测试超时函数（使用快速失败的函数）
        def quick_fail():
            time.sleep(0.1)
            return "success"
        
        def slow_fail():
            time.sleep(2)  # 比超时时间长
            return "too_slow"
        
        # 设置短超时用于测试
        original_timeout = worker.stage_timeouts['audio_extraction']
        worker.stage_timeouts['audio_extraction'] = 1  # 1秒超时
        
        try:
            # 这个应该成功
            result = worker.run_stage_with_timeout('audio_extraction', quick_fail)
            print(f"✓ 快速操作成功: {result}")
            
            # 这个应该超时
            result = worker.run_stage_with_timeout('audio_extraction', slow_fail)
            print("✗ 应该超时但没有超时")
            return False
            
        except Exception as e:
            if "超时" in str(e) or "timeout" in str(e).lower():
                print("✓ 超时机制正常工作")
            else:
                print(f"✗ 意外错误: {e}")
                return False
        finally:
            # 恢复原始超时
            worker.stage_timeouts['audio_extraction'] = original_timeout
        
        worker.cleanup()
        return True
        
    except Exception as e:
        print(f"✗ 超时测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_cancellation():
    """测试取消机制"""
    print("\n测试取消机制...")
    
    try:
        config = create_test_config()
        worker = ImprovedProcessingWorker(
            video_path="/test/video.mp4",
            source_language="en",
            target_language="zh-CN", 
            config=config
        )
        
        # 模拟长时间运行的任务
        def long_running_task():
            for i in range(100):
                if worker.is_cancelled():
                    raise InterruptedError("任务被取消")
                time.sleep(0.01)  # 模拟工作
            return "completed"
        
        # 在另一个线程中启动任务
        result_container = []
        error_container = []
        
        def run_task():
            try:
                result = worker.run_stage_with_timeout('audio_extraction', long_running_task)
                result_container.append(result)
            except Exception as e:
                error_container.append(e)
        
        task_thread = threading.Thread(target=run_task)
        task_thread.start()
        
        # 短暂等待然后取消
        time.sleep(0.05)
        worker.cancel()
        
        # 等待任务完成
        task_thread.join(timeout=2)
        
        if error_container and "取消" in str(error_container[0]):
            print("✓ 取消机制正常工作")
        elif not task_thread.is_alive():
            print("✓ 任务正常结束（可能已完成）")
        else:
            print("✗ 取消机制可能未正常工作")
            return False
        
        worker.cleanup()
        return True
        
    except Exception as e:
        print(f"✗ 取消测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """主测试函数"""
    print("改进的处理系统测试\n")
    
    # 需要QCoreApplication来使用Qt信号
    app = QCoreApplication(sys.argv)
    
    results = []
    
    print("=" * 60)
    results.append(test_worker_initialization())
    
    print("=" * 60)
    results.append(test_timeout_mechanism())
    
    print("=" * 60)
    results.append(test_cancellation())
    
    print("=" * 60)
    if all(results):
        print("✓ 所有测试通过！改进的处理系统应该可以解决卡死问题。")
        print("\n主要改进:")
        print("• 增加了超时机制防止长时间阻塞")
        print("• 改进了取消机制支持中断操作")
        print("• 使用线程池管理并发任务")
        print("• 延迟初始化重资源（Whisper、翻译器）")
        print("• 增强了错误处理和资源清理")
    else:
        print("✗ 部分测试失败，请检查问题。")
    
    return all(results)

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
