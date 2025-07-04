#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import os
import tempfile
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def test_subtitle_generation_fix():
    """测试字幕生成修复"""
    print("测试字幕生成修复...")
    
    try:
        from app.core.subtitle import SubtitleProcessor
        
        processor = SubtitleProcessor()
        
        # 测试数据
        test_segments = [
            {'start': 0.0, 'end': 5.0, 'text': 'Hello world'},
            {'start': 5.0, 'end': 10.0, 'text': 'This is a test'},
            {'start': 10.0, 'end': 15.0, 'text': 'Subtitle generation'}
        ]
        
        print("1. 测试 create_from_segments:")
        segments = processor.create_from_segments(test_segments)
        print(f"✓ 创建了 {len(segments)} 个字幕段")
        print(f"  返回类型: {type(segments)}")
        
        print("\n2. 测试 save_to_file:")
        with tempfile.NamedTemporaryFile(suffix='.srt', delete=False) as tmp_file:
            temp_path = tmp_file.name
        
        try:
            saved_path = processor.save_to_file(temp_path, format_type='srt')
            print(f"✓ 保存字幕文件: {saved_path}")
            print(f"  返回类型: {type(saved_path)}")
            
            # 检查文件是否存在
            if os.path.exists(saved_path):
                print("✓ 字幕文件成功创建")
                with open(saved_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    print(f"  文件内容预览:\n{content[:200]}...")
            else:
                print("✗ 字幕文件未创建")
                return False
        finally:
            # 清理临时文件
            try:
                os.unlink(temp_path)
            except:
                pass
        
        print("\n3. 测试 os.path.basename 兼容性:")
        basename = os.path.basename(saved_path)
        print(f"✓ os.path.basename 正常工作: {basename}")
        
        return True
        
    except Exception as e:
        print(f"✗ 字幕生成测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_translation_fallback():
    """测试翻译回退机制"""
    print("\n测试翻译回退机制...")
    
    try:
        from app.core.translation import TranslationManager, FallbackTranslator
        
        print("1. 测试回退翻译器:")
        fallback = FallbackTranslator()
        
        if fallback.is_available():
            print("✓ 回退翻译器可用")
        else:
            print("✗ 回退翻译器不可用")
            return False
        
        print("\n2. 测试翻译管理器初始化:")
        # 不提供任何 API 密钥，强制使用回退
        manager = TranslationManager(api_keys={})
        
        print(f"✓ 翻译管理器初始化成功")
        print(f"  可用服务: {list(manager.services.keys())}")
        print(f"  服务优先级: {manager.service_priority}")
        
        print("\n3. 测试翻译功能:")
        test_text = "Hello, this is a test translation."
        result = manager.translate(
            text=test_text,
            source_lang="en",
            target_lang="zh-CN"
        )
        
        print(f"✓ 翻译请求完成")
        print(f"  原文: {result.original_text}")
        print(f"  译文: {result.translated_text}")
        print(f"  服务: {result.service}")
        print(f"  置信度: {result.confidence}")
        
        if result.service in ["fallback", "emergency_fallback"]:
            print("✓ 正确使用了回退翻译器")
        else:
            print(f"? 使用了其他服务: {result.service}")
        
        return True
        
    except Exception as e:
        print(f"✗ 翻译回退测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_improved_processing_integration():
    """测试改进处理器的集成"""
    print("\n测试改进处理器集成...")
    
    try:
        # 模拟翻译结果数据
        mock_translation_result = {
            'original_segments': [
                {'start': 0.0, 'end': 5.0, 'text': 'Original text 1'},
                {'start': 5.0, 'end': 10.0, 'text': 'Original text 2'}
            ],
            'translated_texts': [
                'Translated text 1',
                'Translated text 2'
            ]
        }
        
        print("1. 模拟字幕生成阶段:")
        
        from app.core.subtitle import SubtitleProcessor
        
        # 模拟字幕生成逻辑
        processor = SubtitleProcessor()
        original_segments = mock_translation_result.get('original_segments', [])
        translated_texts = mock_translation_result.get('translated_texts', [])
        
        # 创建字幕段
        subtitle_segments = []
        for segment, translated_text in zip(original_segments, translated_texts):
            subtitle_segments.append({
                'start': segment.get('start', 0),
                'end': segment.get('end', 0),
                'text': translated_text
            })
        
        print(f"✓ 创建了 {len(subtitle_segments)} 个字幕段")
        
        # 先创建字幕段，然后保存到文件
        processor.create_from_segments(subtitle_segments)
        
        # 生成输出文件路径
        video_name = "test_video"
        subtitle_path = os.path.join(tempfile.gettempdir(), f"{video_name}_subtitles.srt")
        
        # 保存字幕文件
        saved_path = processor.save_to_file(subtitle_path, format_type='srt')
        
        print(f"✓ 字幕文件保存成功: {os.path.basename(saved_path)}")
        
        # 清理测试文件
        try:
            os.unlink(saved_path)
        except:
            pass
        
        return True
        
    except Exception as e:
        print(f"✗ 改进处理器集成测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """主测试函数"""
    print("翻译和字幕生成修复验证\n")
    
    results = []
    
    print("=" * 60)
    results.append(test_subtitle_generation_fix())
    
    print("=" * 60)
    results.append(test_translation_fallback())
    
    print("=" * 60)
    results.append(test_improved_processing_integration())
    
    print("=" * 60)
    if all(results):
        print("✓ 所有测试通过！翻译和字幕生成问题已修复。")
        print("\n修复内容:")
        print("• 修正了字幕生成的方法调用顺序")
        print("• 添加了回退翻译器，避免翻译完全失败")
        print("• 改进了错误处理和日志记录")
        print("• 确保 os.path.basename 接收正确的字符串参数")
        print("\n现在应用程序应该可以完成整个处理流程了。")
    else:
        print("✗ 部分测试失败，请检查问题。")

if __name__ == "__main__":
    main()
