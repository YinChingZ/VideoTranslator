# 测试索引

本项目将“默认可信门禁”和“历史手工验证脚本”分开。判断一次改动是否通过，
以仓库根目录执行的默认 pytest 与 CI 配置为准，不以旧脚本打印的勾选、返回的
布尔值或单次本机媒体演示为准。

## 默认可信门禁

`pyproject.toml` 将默认收集范围限制为 `tests/unit/`，文件模式为
`test_*.py`。`tests/conftest.py` 进一步排除尚未现代化的 legacy 模块，并设置：

- 临时 HOME / USERPROFILE / XDG 配置目录，避免测试写入用户真实配置；
- `QT_QPA_PLATFORM=offscreen`，供 Qt 测试在 CI 无显示环境运行；
- null keyring，避免弹出系统凭据对话框；
- `--strict-config`、`--strict-markers`、严格 xfail 和 importlib 导入模式。

运行门禁：

```bash
python -m pytest -q
```

先确认当前实际收集项：

```bash
python -m pytest --collect-only -q
```

不要在文档中固化测试数量；新增或拆分可信测试后，数量会正常变化。

## 可信测试覆盖的契约

以下按职责列出当前默认收集的重点。精确测试名以 `--collect-only` 输出为准。

| 领域 | 重点模块 | 主要保证 |
| --- | --- | --- |
| 后台导出 | `test_async_export.py` | GUI 不阻塞、重复任务拒绝、覆盖确认、取消不破坏目标 |
| 音频 | `test_audio_production.py` | 分块读写、SoundFile 输出和打开失败清理 |
| 检查点 | `test_checkpoint_production.py` | 设置绑定、产物校验、原子私有写入、路径规范化 |
| 配置安全 | `test_config_security.py` | 密钥不序列化、旧明文密钥迁移 |
| 打包 | `test_packaging_contract.py` | 构建元数据、GUI 入口、依赖层和版本一致性 |
| 语音识别 | `test_speech_production.py` | 无 vendor 目录依赖、可选 Whisper 错误信息、标准包加载 |
| 字幕 | `test_subtitle_language_modes.py` 及数据流回归 | 三种语言模式、片段数据转换与显示逻辑 |
| 编辑器 | `test_subtitle_editor_optional_playback.py` | 可选播放后端、快捷键、多选合并/拆分后的数据一致性 |
| 翻译 | `test_translation_production.py` | OpenAI/Google 协议、失败元数据、批量故障转移 |
| 启动健康检查 | `test_system_health_contract.py` | 启动不做同步网络探测、speech 缺失只警告 |
| 视觉与访问性 | `test_visual_system.py` | 对比度、主题、矢量图标回退、键盘拖放区 |
| 测试工程 | `test_test_suite_contract.py` | 默认测试不返回值、不在导入阶段污染 `sys.modules` |

默认集还包含少量已经具备真实断言的数据流和字幕显示回归。它们会自动出现在
收集输出中，不需要维护第二份易过期的逐函数清单。

## 与 CI 一致的本地命令

```bash
# 安装 CI 所需依赖
python -m pip install -e ".[dev]"

# 阻断语法错误、未定义名称等 correctness 问题
ruff check --select E9,F63,F7,F82 app main.py scripts tests

# 默认可信测试
python -m pytest -q

# 仓库布局契约
python scripts/verify_organization.py
```

CI 使用 Python 3.11，并设置 offscreen Qt、Agg Matplotlib 和 null keyring。
工作流定义位于 `.github/workflows/ci.yml`。

## 定向运行

```bash
# 一个可信模块
python -m pytest -q tests/unit/test_translation_production.py

# 一个测试函数
python -m pytest -q \
  tests/unit/test_async_export.py::test_video_export_cancellation_stops_child_and_preserves_destination

# 查看失败时的完整输出
python -m pytest -vv -s tests/unit/test_checkpoint_production.py

# 覆盖率报告（没有固定百分比门槛）
python -m pytest --cov=app --cov-report=term-missing
```

GUI 测试优先使用 `pytest-qt`、Qt 信号等待和确定性 mock；不要依赖任意
`sleep`。媒体测试应生成最小临时 fixture 或 mock FFmpeg 边界，不应假设开发者
机器存在某个视频、VLC 窗口或 API 密钥。

## Legacy opt-in

`tests/conftest.py` 中的 `LEGACY_TEST_MODULES` 是历史修复脚本。它们可能存在以下
一种或多种情况：

- 测试函数返回 `True`/`False`，但 pytest 会忽略返回值；
- 捕获异常后只打印，不让测试失败；
- 复制生产逻辑而不是调用生产代码；
- 依赖本机媒体、VLC、窗口焦点、网络或真实 API；
- 通过全局 `sys.modules` 替换造成收集顺序依赖；
- 适合人工诊断，不适合作为回归门禁。

只有在调查历史问题时才显式启用，推荐指定单个文件：

```bash
VIDEO_TRANSLATOR_RUN_LEGACY_TESTS=1 \
  python -m pytest -q -s tests/unit/test_export_video_fix.py
```

Windows PowerShell：

```powershell
$env:VIDEO_TRANSLATOR_RUN_LEGACY_TESTS = "1"
python -m pytest -q -s tests/unit/test_export_video_fix.py
```

启用 legacy 不会自动让这些脚本变得可信。其结果只能作为诊断线索，不应替代
默认门禁。`tests/run_all_tests.py` 也不是当前质量入口。

## Integration 与 debug 目录

- `tests/integration/` 保存历史跨模块验证脚本；默认 pytest 和 CI 不收集它们。
- `tests/debug/` 保存 VLC、烧入字幕、视频切换等人工诊断工具；可能打开窗口、
  调用本机 FFmpeg/VLC 或要求准备媒体。

运行前先阅读目标文件，并显式指定路径。例如：

```bash
python -m pytest -q -s tests/integration/final_export_test.py
python tests/debug/diagnose_vlc_embedding.py
```

这些命令不属于 CI 门禁。若某个历史场景需要长期保障，应把它改写为：调用真实
生产接口、使用临时文件或 mock 外部边界、对结果 `assert`，然后移出 legacy
排除列表。

## 新增测试的准入要求

1. 测试必须以断言或未捕获异常表示失败，不能从 `test_*` 返回状态值。
2. 测试生产接口，不复制一份待测算法到测试文件。
3. 不读取用户真实 HOME，不写用户钥匙串，不需要真实 API 密钥。
4. Qt 和后台线程必须有有界等待与清理；失败也不能遗留线程或子进程。
5. 临时媒体和数据库使用 `tmp_path`，测试结束后由 fixture 回收。
6. 外部协议用录制的最小响应或 mock 验证请求契约；真正的联网测试必须另行标记。
7. 新测试默认应被收集；除非有书面理由，不得把新文件加入
   `LEGACY_TEST_MODULES`。
