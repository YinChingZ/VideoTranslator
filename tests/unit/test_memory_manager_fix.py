#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import os
from unittest.mock import Mock, patch

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def test_memory_manager_types():
    """测试内存管理器的类型问题修复"""
    print("测试内存管理器类型修复...")
    
    try:
        from app.utils.memory_manager import MemoryLimiter, memory_managed_operation
        
        print("1. 测试 MemoryLimiter 类型处理...")
        
        # 测试正确的数字参数
        limiter1 = MemoryLimiter(1024.0)  # float
        print(f"✓ MemoryLimiter 接受 float: {limiter1.max_memory_mb}")
        
        limiter2 = MemoryLimiter(1024)    # int
        print(f"✓ MemoryLimiter 接受 int: {limiter2.max_memory_mb}")
        
        # 测试类型检查
        assert isinstance(limiter1.max_memory_mb, (int, float))
        assert isinstance(limiter2.max_memory_mb, (int, float))
        print("✓ MemoryLimiter 正确处理数字类型")
        
        print("\n2. 测试 memory_managed_operation 上下文管理器...")
        
        # 测试上下文管理器用法
        with memory_managed_operation(max_memory_mb=1024) as limiter:
            print(f"✓ memory_managed_operation 上下文管理器正常工作")
            print(f"  限制器类型: {type(limiter)}")
            print(f"  内存限制: {limiter.max_memory_mb}MB")
        
        print("✓ memory_managed_operation 上下文正常退出")
        
        print("\n3. 测试模拟的语音识别场景...")
        
        # 模拟内存统计
        mock_stats = Mock()
        mock_stats.process_mb = 500.0  # 确保是float
        mock_stats.percent = 60.0
        
        with patch('app.utils.memory_manager.MemoryMonitor') as mock_monitor_class:
            mock_monitor = Mock()
            mock_monitor.get_memory_stats.return_value = mock_stats
            mock_monitor_class.return_value = mock_monitor
            
            # 测试内存检查
            limiter = MemoryLimiter(1024)
            result = limiter.check_memory_limit()
            
            print(f"✓ 内存检查正常: {result}")
            print(f"  进程内存: {mock_stats.process_mb}MB")
            print(f"  内存限制: {limiter.max_memory_mb}MB")
            print(f"  通过检查: {mock_stats.process_mb <= limiter.max_memory_mb}")
        
        return True
        
    except Exception as e:
        print(f"✗ 内存管理器测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_speech_transcribe_fix():
    """测试语音转写方法的修复"""
    print("\n测试语音转写方法修复...")
    
    try:
        # 模拟必要的模块
        with patch('whisper.load_model') as mock_load_model:
            with patch('torch.cuda.is_available', return_value=False):
                with patch('app.utils.memory_manager.MemoryMonitor') as mock_monitor_class:
                    
                    # 设置模拟
                    mock_model = Mock()
                    mock_model.transcribe.return_value = {
                        'text': 'Test transcription',
                        'segments': [{'start': 0, 'end': 5, 'text': 'Test transcription'}],
                        'language': 'en'
                    }
                    mock_load_model.return_value = mock_model
                    
                    mock_stats = Mock()
                    mock_stats.process_mb = 500.0
                    mock_stats.percent = 60.0
                    
                    mock_monitor = Mock()
                    mock_monitor.get_memory_stats.return_value = mock_stats
                    mock_monitor_class.return_value = mock_monitor
                    
                    # 创建临时测试文件
                    import tempfile
                    with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as temp_file:
                        temp_path = temp_file.name
                    
                    try:
                        from app.core.speech import SpeechRecognizer
                        
                        recognizer = SpeechRecognizer(model='base')
                        
                        # 测试转写方法
                        result = recognizer.transcribe(temp_path, language='en')
                        
                        print("✓ SpeechRecognizer.transcribe() 方法正常工作")
                        print(f"  结果类型: {type(result)}")
                        print(f"  包含文本: {'text' in result}")
                        print(f"  包含片段: {'segments' in result}")
                        
                        return True
                        
                    finally:
                        # 清理临时文件
                        try:
                            os.unlink(temp_path)
                        except:
                            pass
                            
    except Exception as e:
        print(f"✗ 语音转写测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    print("内存管理器类型错误修复验证\n")
    
    print("=" * 60)
    test1_result = test_memory_manager_types()
    
    print("=" * 60)
    test2_result = test_speech_transcribe_fix()
    
    print("=" * 60)
    if test1_result and test2_result:
        print("✓ 所有修复验证通过！")
        print("\n修复内容:")
        print("• 修正了 memory_managed_operation 的错误使用方式")
        print("• 将装饰器用法改为上下文管理器用法")
        print("• 确保内存限制参数为数字类型而非字符串")
        print("• 修复了语音转写方法的内存管理")
        print("\n现在应用程序应该不会再出现类型比较错误了。")
    else:
        print("✗ 部分修复验证失败，请检查问题。")

if __name__ == "__main__":
    main()
