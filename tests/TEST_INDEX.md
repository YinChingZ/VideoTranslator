# 测试索引和分类

## 单元测试列表

### 配置相关测试
- test_config.py - 配置测试
- test_config_import.py - 配置导入测试
- test_appconfig_setdefault_fix.py - 应用配置设置默认值修复测试

### 音频处理测试
- test_audio_fix.py - 音频修复测试

### 字幕相关测试
- test_subtitle_*.py - 各种字幕功能测试
- test_embed_subtitles.py - 嵌入字幕测试
- test_burn_*.py - 字幕烧录测试

### GUI测试
- test_gui_integration.py - GUI集成测试
- test_ui_fixes.py - UI修复测试
- test_subtitle_editor_fix.py - 字幕编辑器修复测试
- test_settings_dialog_fix.py - 设置对话框修复测试

### 视频处理测试
- test_video_switching_fix.py - 视频切换修复测试
- test_vlc_*.py - VLC相关测试

### 撤销重做测试
- test_undo_redo*.py - 撤销重做功能测试

### 导出功能测试
- test_export_*.py - 导出功能测试

### 核心功能测试
- test_core_functionality.py - 核心功能测试
- test_imports.py - 导入测试
- test_memory_manager_fix.py - 内存管理修复测试

## 集成测试列表

### 完整流程测试
- final_export_test.py - 最终导出测试
- final_verification.py - 最终验证

### 系统验证测试
- verify_fixes.py - 修复验证
- verify_video_switching_fix.py - 视频切换修复验证
- validate_refactor.py - 重构验证

## 调试脚本列表

### 字幕调试
- debug_burn_subtitles.py - 字幕烧录调试
- debug_subprocess_burn.py - 子进程烧录调试
- check_vlc_subtitles.py - VLC字幕检查

### 视频处理调试
- diagnose_video_switching.py - 视频切换诊断
- diagnose_vlc_embedding.py - VLC嵌入诊断

### 演示脚本
- demo_progress.py - 进度演示
- vlc_subtitle_fix_demo.py - VLC字幕修复演示

## 测试运行指南

1. 运行所有测试：`python tests/run_all_tests.py`
2. 运行单元测试：`python -m pytest tests/unit/`
3. 运行集成测试：`python -m pytest tests/integration/`
4. 运行调试脚本：直接运行 `python tests/debug/script_name.py`
