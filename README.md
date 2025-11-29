# VideoTranslator - 智能视频翻译系统

## 项目简介

VideoTranslator是一个基于PyQt5的智能视频翻译桌面应用程序，集成了OpenAI Whisper语音识别引擎和多种翻译API，为用户提供从视频音频提取、语音识别、文本翻译到字幕生成和视频导出的完整视频翻译解决方案。

### 核心功能

- **🎵 音频处理**: 自动从视频中提取音频，支持多种音频格式
- **🗣️ 语音识别**: 集成OpenAI Whisper引擎，支持多语言高精度语音转文本
- **🌐 智能翻译**: 支持OpenAI、DeepL、Google等多种翻译API
- **📝 字幕编辑**: 可视化字幕编辑器，支持时间轴调整和样式设置
- **🎬 视频导出**: 支持字幕烧录和软字幕嵌入两种导出方式
- **⚡ 性能优化**: 内存管理、多线程处理、检查点恢复机制

### 技术架构

- **前端框架**: PyQt5 - 跨平台桌面GUI框架
- **音频处理**: FFmpeg - 视频/音频处理工具链
- **语音识别**: OpenAI Whisper - 高精度多语言语音识别
- **翻译引擎**: 多API支持 (OpenAI GPT、DeepL、Google Translate)
- **字幕格式**: 支持SRT、VTT、ASS等多种字幕格式
- **数据库**: SQLite - 本地缓存和配置存储

## 项目架构

### 主要目录结构

```
VideoTranslator/
├── app/                    # 应用程序核心代码
│   ├── core/              # 核心业务逻辑
│   │   ├── audio.py       # 音频处理模块
│   │   ├── speech.py      # 语音识别模块 (Whisper集成)
│   │   ├── translation.py # 翻译处理模块
│   │   ├── subtitle.py    # 字幕处理模块
│   │   └── video.py       # 视频处理模块
│   ├── gui/               # 图形用户界面
│   │   ├── main_window.py      # 主窗口
│   │   ├── video_import.py     # 视频导入界面
│   │   ├── processing.py       # 处理进度界面
│   │   ├── subtitle_editor.py  # 字幕编辑器
│   │   └── export_dialog.py    # 导出设置对话框
│   ├── utils/             # 实用工具模块
│   │   ├── logger.py           # 日志系统
│   │   ├── temp_files.py       # 临时文件管理
│   │   ├── memory_manager.py   # 内存管理
│   │   ├── checkpoint.py       # 检查点系统
│   │   └── system_health_checker.py # 系统健康检查
│   ├── resources/         # 资源文件
│   │   ├── icons/         # 图标资源
│   │   ├── styles.py      # 样式管理
│   │   └── icons.py       # 图标管理
│   └── config.py          # 配置管理
├── tests/                 # 测试套件
│   ├── unit/             # 单元测试 (45个测试文件)
│   ├── integration/      # 集成测试 (6个测试文件)
│   ├── debug/            # 调试脚本 (7个调试工具)
│   └── TEST_INDEX.md     # 测试索引文档
├── docs/                 # 项目文档
│   ├── fix-reports/      # 修复报告 (11个报告)
│   ├── analysis/         # 分析报告 (8个报告)
│   ├── IMPROVEMENT_PLAN.md
│   └── REFACTOR_REPORT.md
├── model/                # AI模型文件
│   └── whisper/          # Whisper模型 (本地集成)
├── logs/                 # 应用日志
├── scripts/              # 辅助脚本
└── 配置文件              # 项目配置
    ├── main.py           # 应用程序入口
    ├── requirements.txt  # Python依赖
    ├── pyproject.toml    # 项目配置
    └── README.md         # 项目说明
```

## 核心模块详解

### 1. 核心业务逻辑 (app/core/)

#### 音频处理模块 (audio.py)
- 从视频文件中提取音频轨道
- 支持多种音频格式转换
- 音频质量优化和噪声处理

#### 语音识别模块 (speech.py) 
- 集成OpenAI Whisper引擎
- 支持多语言自动识别
- 内存管理和GPU加速优化
- 支持模型选择 (tiny/base/small/medium/large)

#### 翻译处理模块 (translation.py)
- 多API支持: OpenAI GPT、DeepL、Google Translate
- 智能缓存机制减少API调用
- 批量翻译和错误恢复
- 术语词典和上下文处理

#### 字幕处理模块 (subtitle.py)
- 支持SRT、VTT、ASS等多种字幕格式
- 时间轴同步和调整
- 字幕样式和位置设置
- 字幕验证和错误检查

#### 视频处理模块 (video.py)
- 视频元数据提取
- 字幕烧录 (硬字幕)
- 字幕嵌入 (软字幕)
- 视频格式转换和压缩

### 2. 图形用户界面 (app/gui/)

#### 主窗口 (main_window.py)
- 应用程序主界面和工作流控制
- 菜单系统和快捷键支持
- 状态栏和通知系统
- 设置对话框和配置管理

#### 视频导入界面 (video_import.py)
- 拖放式视频文件导入
- 视频预览和信息显示
- 批量导入支持

#### 处理进度界面 (processing.py)
- 实时处理进度显示
- 多阶段任务状态监控
- 取消和暂停功能
- 错误处理和恢复机制

#### 字幕编辑器 (subtitle_editor.py)
- 可视化字幕编辑
- 时间轴拖拽调整
- 实时预览功能
- 撤销/重做操作

#### 导出设置对话框 (export_dialog.py)
- 导出格式选择
- 质量参数设置
- 路径和文件名配置

### 3. 实用工具模块 (app/utils/)

#### 系统健康检查 (system_health_checker.py)
- 启动前系统环境检查
- 依赖项验证和兼容性检测
- 资源可用性监控
- 详细的诊断报告

#### 内存管理 (memory_manager.py)
- 内存使用监控
- 自动垃圾回收
- 大文件处理优化
- 内存泄漏检测

#### 检查点系统 (checkpoint.py)
- 处理进度保存
- 意外中断恢复
- 增量处理支持
- 数据完整性验证

#### 临时文件管理 (temp_files.py)
- 临时文件生命周期管理
- 自动清理机制
- 磁盘空间优化

#### 日志系统 (logger.py)
- 分级日志记录
- 日志轮转和压缩
- 错误追踪和调试信息

### 4. 资源管理 (app/resources/)

#### 图标管理 (icons.py)
- 主题化图标系统
- SVG图标支持
- 高DPI显示适配
- 动态图标缓存

#### 样式管理 (styles.py)
- 深色/浅色主题支持
- 跨平台样式兼容
- 动态样式切换
- 自定义样式扩展

## 技术特性

### 性能优化
- **多线程处理**: 音频提取、语音识别、翻译并行处理
- **内存管理**: 大文件分块处理，智能缓存策略
- **GPU加速**: 支持CUDA加速的Whisper推理
- **检查点恢复**: 处理中断后可从断点继续

### 可靠性保障
- **错误处理**: 全面的异常捕获和恢复机制
- **数据验证**: 多层数据完整性检查
- **备份机制**: 自动保存和版本控制
- **健康监控**: 实时系统状态监控

### 用户体验
- **界面友好**: 直观的工作流程设计
- **进度可视**: 详细的处理进度反馈
- **快捷操作**: 键盘快捷键和右键菜单
- **主题适配**: 深色/浅色主题自动切换

## 环境要求

### 系统要求
- **操作系统**: Windows 10/11, macOS 10.14+, Linux (Ubuntu 18.04+)
- **Python版本**: 3.8 或更高版本
- **内存**: 建议8GB以上 (处理大文件时)
- **存储**: 至少5GB可用空间
- **网络**: 稳定的互联网连接 (用于翻译API)

### 核心依赖
- **PyQt5**: 跨平台GUI框架
- **OpenAI Whisper**: 语音识别引擎
- **FFmpeg**: 音视频处理工具
- **PyTorch**: 深度学习框架 (Whisper依赖)
- **Requests**: HTTP请求库
- **SQLite**: 本地数据库

### 可选依赖
- **CUDA**: GPU加速支持
- **VLC**: 视频播放器组件
- **OpenCV**: 图像处理 (高级功能)

## 安装指南

### 1. 克隆项目
```bash
[git clone https://github.com/yourusername/VideoTranslator.git](https://github.com/YinChingZ/VideoTranslator.git)
cd VideoTranslator
```

### 2. 安装依赖
```bash
# 安装Python依赖
pip install -r requirements.txt

# 安装FFmpeg (Windows)
# 下载并安装FFmpeg，确保添加到PATH环境变量

# 安装FFmpeg (macOS)
brew install ffmpeg

# 安装FFmpeg (Ubuntu)
sudo apt update
sudo apt install ffmpeg
```

### 3. 配置API密钥
在应用程序设置中配置您的翻译API密钥：
- OpenAI API密钥
- DeepL API密钥
- Google Translate API密钥

### 4. 运行应用程序
```bash
python main.py
```

## 使用流程

### 1. 视频导入
- 拖拽视频文件到应用窗口
- 或通过菜单选择视频文件
- 支持的格式: MP4, AVI, MOV, MKV等

### 2. 语言设置
- 选择源语言 (可自动检测)
- 选择目标语言
- 配置Whisper模型大小

### 3. 处理阶段
- **音频提取**: 从视频中提取音频轨道
- **语音识别**: 使用Whisper进行语音转文本
- **文本翻译**: 调用翻译API进行文本翻译
- **字幕生成**: 生成带时间轴的字幕文件

### 4. 字幕编辑
- 在字幕编辑器中调整时间轴
- 修改翻译文本
- 设置字幕样式和位置

### 5. 视频导出
- 选择导出格式 (硬字幕/软字幕)
- 设置视频质量参数
- 开始导出最终视频

## 测试体系

### 测试分类

#### 单元测试 (tests/unit/) - 45个测试文件
测试单个模块和功能组件的正确性：

**配置管理测试**
- `test_config*.py`: 配置系统和参数管理
- `test_appconfig_setdefault_fix.py`: 配置默认值设置

**音频处理测试**
- `test_audio_fix.py`: 音频提取和格式转换

**字幕处理测试**
- `test_subtitle_*.py`: 字幕解析、生成和格式转换
- `test_embed_subtitles.py`: 字幕嵌入功能
- `test_burn_*.py`: 字幕烧录功能

**GUI组件测试**
- `test_gui_integration.py`: GUI集成测试
- `test_ui_fixes.py`: 界面修复验证
- `test_subtitle_editor_fix.py`: 字幕编辑器功能
- `test_settings_dialog_fix.py`: 设置对话框

**视频处理测试**
- `test_video_switching_fix.py`: 视频切换功能
- `test_vlc_*.py`: VLC播放器集成

**核心功能测试**
- `test_core_functionality.py`: 核心业务逻辑
- `test_memory_manager_fix.py`: 内存管理
- `test_translation_subtitle_fix.py`: 翻译和字幕集成

**撤销重做测试**
- `test_undo_redo*.py`: 撤销重做功能测试

**导出功能测试**
- `test_export_*.py`: 视频导出功能测试

#### 集成测试 (tests/integration/) - 6个测试文件
测试组件间的协作和端到端流程：

**完整流程测试**
- `final_export_test.py`: 完整的视频翻译导出流程
- `final_verification.py`: 最终功能验证

**系统验证测试**
- `verify_fixes.py`: 修复功能验证
- `verify_video_switching_fix.py`: 视频切换修复验证
- `validate_refactor.py`: 重构后系统验证

#### 调试工具 (tests/debug/) - 7个调试脚本
用于问题诊断和功能演示：

**VLC相关调试**
- `check_vlc_subtitles.py`: VLC字幕显示检查
- `diagnose_vlc_embedding.py`: VLC嵌入诊断
- `vlc_subtitle_fix_demo.py`: VLC字幕修复演示

**视频处理调试**
- `debug_burn_subtitles.py`: 字幕烧录调试
- `diagnose_video_switching.py`: 视频切换诊断

**功能演示**
- `demo_progress.py`: 进度显示演示

### 文档体系

#### 修复报告 (docs/fix-reports/) - 11个报告
记录各种功能修复的详细过程：

- **完整修复摘要**: `COMPLETE_FIX_SUMMARY.md`
- **导出功能修复**: `EXPORT_*_FIX_REPORT.md`
- **字幕系统修复**: `SUBTITLE_FIX_REPORT.md`
- **界面修复**: `UI_FIXES_REPORT.md`
- **视频切换修复**: `VIDEO_SWITCHING_FIX_REPORT.md`
- **VLC集成修复**: `VLC_*_FIX_REPORT.md`
- **重构总结**: `REFACTOR_SUMMARY.md`

#### 分析报告 (docs/analysis/) - 8个报告
项目技术分析和改进建议：

- **项目分析**: `PROJECT_ANALYSIS_REPORT.md`
- **技术债务分析**: `TECHNICAL_DEBT_ANALYSIS.md`
- **撤销重做分析**: `UNDO_REDO_*_REPORT.md`
- **性能分析数据**: 多个JSON格式的分析数据文件

## 运行和测试

### 启动应用程序
```bash
# 启动主应用
python main.py

# 启动并打开指定视频文件
python main.py path/to/video.mp4

# 启动调试模式
python main.py --debug
```

### 运行测试套件
```bash
# 运行所有测试
python tests/run_all_tests.py

# 运行单元测试
python -m pytest tests/unit/ -v

# 运行集成测试
python -m pytest tests/integration/ -v

# 运行特定测试
python tests/unit/test_core_functionality.py

# 运行调试脚本
python tests/debug/demo_progress.py
```

### 系统诊断
```bash
# 运行系统诊断
python tests/test.py

# 验证项目组织
python scripts/verify_organization.py
```

## 配置选项

### 应用程序配置
- **Whisper模型**: 选择语音识别模型大小
- **翻译提供商**: 配置翻译API服务
- **质量设置**: 音频和视频质量参数
- **界面主题**: 深色/浅色主题切换

### 高级配置
- **内存限制**: 设置内存使用上限
- **缓存策略**: 配置缓存大小和过期时间
- **并发设置**: 调整线程池大小
- **日志级别**: 设置日志详细程度

## 故障排除

### 常见问题

**1. FFmpeg未找到**
- 确保FFmpeg已安装并添加到PATH环境变量
- Windows: 下载FFmpeg官方版本
- macOS: `brew install ffmpeg`
- Linux: `sudo apt install ffmpeg`

**2. Whisper模型加载失败**
- 检查网络连接，首次使用需要下载模型
- 确保有足够的磁盘空间存储模型
- 尝试使用较小的模型 (如tiny或base)

**3. 翻译API错误**
- 验证API密钥是否正确
- 检查API配额是否用完
- 确认网络连接稳定

**4. 内存不足**
- 关闭其他占用内存的应用程序
- 选择较小的Whisper模型
- 处理较短的视频片段

**5. 字幕时间轴不准确**
- 检查原始音频质量
- 尝试不同的Whisper模型
- 手动调整字幕时间轴

### 日志分析
应用程序会在`logs/`目录中记录详细的运行日志，包括：
- 系统健康检查结果
- 处理过程中的错误和警告
- 性能统计信息
- 调试信息

## 开发指南

### 开发环境设置
```bash
# 安装开发依赖
pip install -r requirements.txt

# 安装代码格式化工具
pip install black flake8 mypy

# 运行代码格式化
black app/ tests/

# 运行类型检查
mypy app/

# 运行代码质量检查
flake8 app/ tests/
```

### 代码结构规范
- 遵循PEP 8代码风格
- 使用类型注解
- 编写完整的文档字符串
- 保持模块间的低耦合
- 实现充分的错误处理

### 测试规范
- 新功能必须有对应的单元测试
- 重要修复需要添加回归测试
- 保持测试覆盖率在80%以上
- 集成测试验证端到端流程

## 贡献指南

### 如何贡献
1. Fork项目仓库
2. 创建功能分支
3. 编写代码和测试
4. 提交Pull Request
5. 参与代码审查

### 报告问题
- 使用GitHub Issues报告Bug
- 提供详细的复现步骤
- 包含系统环境信息
- 附上相关日志文件

### 功能请求
- 在Issues中提出功能请求
- 详细描述需求场景
- 讨论实现方案
- 评估开发工作量

## 许可证

本项目采用MIT许可证，详情请参阅LICENSE文件。

## 项目状态

### 当前版本
- **版本号**: 1.0.0
- **发布日期**: 2025年7月4日
- **稳定性**: 稳定版本

### 功能完成度
- ✅ 视频导入和预览
- ✅ 音频提取和处理
- ✅ 语音识别 (Whisper集成)
- ✅ 多语言翻译
- ✅ 字幕编辑和调整
- ✅ 视频导出 (硬字幕/软字幕)
- ✅ 系统健康检查
- ✅ 内存管理和优化
- ✅ 错误处理和恢复
- ✅ 完整的测试套件

### 近期改进
- 重构了核心模块架构
- 优化了内存管理系统
- 增强了错误处理机制
- 完善了测试覆盖率
- 改进了用户界面交互

### 技术债务
- 部分模块需要进一步优化
- 文档需要持续更新
- 性能基准测试待完善
- 国际化支持有待加强

---
  
**最后更新**: 2025年7月4日  
**联系方式**: 请通过GitHub Issues联系我们
