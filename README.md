# VideoTranslator

VideoTranslator 是一个面向单个视频的桌面字幕工作流：提取音频、用本地
Whisper 转写、调用云端翻译服务、编辑时间轴与文本，最后导出字幕文件或带
字幕的视频。

项目目前处于 **Beta**。主流程、项目文件、恢复检查点和后台导出已经具备，
但它不是无人值守的批处理平台，也不承诺任意媒体编码都可直接处理。下面只
描述当前代码实际提供的能力和边界。

## 当前能力

- 通过文件选择器、拖放或启动参数导入一个视频，并用 FFprobe 读取媒体信息。
- 通过 FFmpeg 提取 16 kHz 单声道音频；音频工具也提供分块读写与重采样能力。
- 使用本地 `openai-whisper` 转写，可选择 `tiny`、`base`、`small`、`medium`
  或 `large` 模型，并在可用时使用 CUDA。
- 使用 OpenAI Responses API、DeepL API 或 Google Cloud Translation Basic v2
  翻译。多个服务都已配置时，管理器可按优先级对失败项进行故障转移。
- 用 SQLite 在本机缓存成功译文；未翻译的原文回退会被明确标记为失败，不会
  缓存成成功结果。
- 编辑字幕原文、译文、开始/结束时间，添加、删除、连续多选合并、拆分片段，
  并检查空文本、重叠和非法时间等问题。
- 直接导入 SRT、VTT、ASS/SSA、YouTube SBV 或 MicroDVD SUB，选好
  对应视频后跳过转写，直接进入编辑器。
- 保存和重新打开 `.vtp` v2 项目；项目记录源视频、语言和字幕片段。
- 导出 SRT、WebVTT、ASS/SSA、YouTube SBV、MicroDVD SUB，或通过 FFmpeg
  嵌入软字幕、烧入硬字幕。
- 导出在后台线程执行；取消 FFmpeg 导出时会终止子进程，临时结果不会覆盖既有
  目标文件。
- 处理按音频提取、语音识别、翻译、字幕生成四个阶段保存检查点，完成后清除。
- 浅色、深色和跟随系统主题；导入区与主要编辑控件支持键盘操作和辅助功能名称。

更详细的模块和数据流见 [架构说明](docs/ARCHITECTURE.md)。

## 明确限制

- 一次只处理一个视频；没有批量导入、任务队列或服务器模式。
- 处理任务没有“暂停”。取消是协作式的：翻译可在片段之间停止，但标准 Whisper
  的一次 `transcribe` 调用和部分 FFmpeg 阶段不能在任意指令处安全中断，因此
  可能要等当前阶段返回。视频导出有独立的可取消 FFmpeg 子进程。
- 编辑器撤销/重做覆盖文本、时间、片段增删、合并、拆分和整体时间轴调整；每次
  打开新视频或项目时历史栈会重置。
- 当前没有离线翻译后端；可用翻译提供商是 OpenAI、DeepL 和 Google。
- 软字幕是否兼容取决于容器；硬字幕是否成功取决于 FFmpeg 的编码器、libass、
  字体和源音频编码。导出对话框不会绕过这些底层限制。
- 未检测到 VLC 时编辑器仅显示由 FFmpeg 异步提取的静态画面，没有实时音视频播放。
- 本项目不附带 API 额度、Whisper 模型或媒体编解码器，也未对所有操作系统、
  GPU 和编码组合做穷尽验证。

## 环境要求

- Python 3.11 或更高版本
- FFmpeg 和 FFprobe，且两个命令都可从 `PATH` 运行
- 一个有图形桌面的 Windows、macOS 或 Linux 环境
- 完整转写流程建议至少 8 GB 内存；模型越大，内存、显存和磁盘需求越高
- 首次下载 Whisper 模型及使用云端翻译时需要网络

先确认外部工具：

```bash
python --version
ffmpeg -version
ffprobe -version
```

常见 FFmpeg 安装方式：

```bash
# macOS（Homebrew）
brew install ffmpeg

# Ubuntu / Debian
sudo apt update
sudo apt install ffmpeg
```

Windows 可使用官方或可信分发包，并将包含 `ffmpeg.exe`、`ffprobe.exe` 的目录
加入 `PATH`。

## 安装

建议在虚拟环境中进行可编辑安装：

```bash
git clone https://github.com/YinChingZ/VideoTranslator.git
cd VideoTranslator

python -m venv .venv
# macOS / Linux
source .venv/bin/activate
# Windows PowerShell
# .venv\Scripts\Activate.ps1

python -m pip install --upgrade pip
python -m pip install -e .
```

`pip install -e .` 是相对轻量的桌面安装：包含 GUI、媒体/字幕处理、云端翻译
适配器和安全密钥存储，但刻意不安装体积很大的 Whisper 与 PyTorch。它适合检查
界面、打开既有 `.vtp` 项目和编辑/导出字幕；要执行从视频到转写的完整流程，
安装 speech extra：

```bash
python -m pip install -e ".[speech]"
```

静音分段/重采样增强与实时播放后端也分层安装：

```bash
python -m pip install -e ".[media]"     # librosa + pydub
python -m pip install -e ".[playback]"  # python-vlc
```

安装项目声明的全部可选运行依赖（Whisper/PyTorch、媒体增强和播放后端）：

```bash
python -m pip install -e ".[full]"
```

`full` 等价于安装 `speech`、`media` 和 `playback` 三组可选运行依赖。

`requirements.txt` 也是完整运行依赖清单，适合不使用 extras 的环境：

```bash
python -m pip install -r requirements.txt
```

开发环境使用：

```bash
python -m pip install -e ".[dev,speech]"
# 或包含所有可选运行依赖
python -m pip install -e ".[dev,full]"
```

PyTorch/CUDA 必须与显卡驱动和平台匹配；有 GPU 需求时，建议先按 PyTorch 官方
说明安装合适构建，再安装本项目。没有 CUDA 时 Whisper 会使用 CPU。

### VLC 的降级行为

VLC 是实时预览后端，`python-vlc` 只是 Python 绑定；系统还需要可加载的 VLC
原生库。代码会延迟导入 VLC，并同时捕获 Python 包缺失与原生库加载失败。VLC
不可用不会阻止项目编辑，预览会降级为 FFmpeg 在后台提取的静态帧。

`python-vlc` 位于 `playback` extra；安装 Python 包不等于系统 VLC 原生库一定可用。

## 启动

安装后可使用 GUI 入口：

```bash
video-translator
video-translator /path/to/video.mp4
video-translator --debug /path/to/video.mp4
```

也可以从源码入口启动：

```bash
python main.py
python main.py /path/to/video.mp4
python main.py --debug /path/to/video.mp4
```

这里的命令行只负责启动 GUI、可选地预先打开一个视频和启用调试日志；没有
无界面的转写/导出 CLI。

启动时会检查 Python 版本、基础 Python 包、FFmpeg/FFprobe、文件系统和系统
资源。缺少 speech extra 会显示警告而不是让字幕编辑能力无法启动；缺少基础包
或 FFmpeg/FFprobe 会被视为环境错误。

## 翻译提供商与密钥

在“设置”中选择提供商并填写对应 API 密钥：

| 提供商 | 当前接口 | 发送的数据 |
| --- | --- | --- |
| OpenAI | Responses API | 单个字幕片段的文本与翻译指令 |
| DeepL | `/v2/translate` | 一个或多个字幕文本与语言代码 |
| Google | Cloud Translation Basic v2 | 一个或多个字幕文本与语言代码 |

GUI 保存的密钥写入操作系统钥匙串，**不会写入**
平台应用配置文件。如果系统钥匙串不可用，密钥只在当前进程内
保留；重新启动后需要再次提供。旧版配置中的明文 `api_keys` 会在加载时尝试迁移
到钥匙串，并从 JSON 中移除。

也可使用环境变量，适合临时环境或 CI：

```bash
export VIDEOTRANSLATOR_OPENAI_API_KEY="..."
export VIDEOTRANSLATOR_DEEPL_API_KEY="..."
export VIDEOTRANSLATOR_GOOGLE_API_KEY="..."
```

Windows PowerShell 对应写法为 `$env:VIDEOTRANSLATOR_OPENAI_API_KEY="..."`。
环境变量会在没有会话内密钥时优先于钥匙串读取。

当首选服务失败时，管理器会尝试其他已经配置的服务。所有服务都不可用时，
返回值会明确带有失败元数据，主处理流程会停止并提示检查密钥、网络或额度，
不会把未变化的原文显示为成功译文。

## 从导入到导出

1. 运行应用，在“设置”中选择 Whisper 模型、翻译提供商并配置密钥。
2. 拖放或选择一个视频；确认 FFprobe 显示的文件名、时长和分辨率。
3. 选择源语言（可自动检测）和目标语言，然后继续。
4. 等待四个阶段：音频提取、语音识别、文本翻译、字幕生成。可以请求取消，
   已完成阶段的有效检查点会保留。
5. 在编辑器中修改原文、译文和时间，或添加、删除、合并、拆分片段；使用验证
   动作检查明显问题。
6. 如需稍后继续人工编辑，保存为 `.vtp` 项目。
7. 打开导出对话框，选择字幕格式、语言模式以及是否嵌入/烧入视频。目标已存在
   时必须明确确认覆盖。
8. 导出在后台进行，可从主窗口取消；成功后最终文件以原子替换方式提交。

如果已有字幕，先在导入页选择视频，再从“文件 → 导入字幕”选择
SRT、VTT、ASS/SSA、SBV 或 MicroDVD SUB，即可跳过第 3–4 步。也可先
选字幕，应用会提示选择其对应的单个视频。

### 三种字幕语言模式

| 模式 | 输出内容 |
| --- | --- |
| 仅原文 `original_only` | 只输出 `original_text` |
| 仅译文 `translation_only` | 优先输出 `translated_text`；该段译文为空时回退为原文 |
| 双语 `bilingual` | 原文和译文都非空时分两行输出 |

模式对 SRT、VTT、ASS/SSA、SBV 和 MicroDVD SUB 导出一致；不同格式使用各自的
换行表示。

### 导出边界

- 字幕文件：导出对话框提供 SRT、VTT、ASS、SSA、YouTube SBV 和 MicroDVD SUB。
- 软字幕：当前后台导出器可靠支持 MP4/MOV、MKV 和 WebM 的对应字幕编码；
  AVI 不作为可靠软字幕容器。GUI 提供 MP4、MKV、MOV、WebM 或跟随源格式。
- 硬字幕：视频会重新编码（通常为 H.264，WebM 为 VP9），音频默认复制。若源
  音频编码与目标容器不兼容，FFmpeg 会明确失败而不是留下半成品。
- 字幕样式主要通过 ASS 烧入体现；系统字体缺失会影响排版。

## 项目文件 v2

`.vtp` 是 UTF-8 JSON，当前结构使用：

```json
{
  "schema": "videotranslator.project",
  "version": 2,
  "video_path": "/absolute/path/to/video.mp4",
  "video_path_relative": "media/video.mp4",
  "source_language": "en",
  "target_language": "zh-CN",
  "segments": []
}
```

每个片段包含开始/结束时间、原文、译文、索引和样式数据。保存使用同目录临时
文件加原子替换，减少进程中断造成的半文件。

项目文件同时记录相对与绝对视频路径，不复制视频、API 密钥、Whisper 模型、
翻译缓存或导出产物。打开时优先使用相对路径，因此项目与媒体目录整体搬移后仍
可直接解析；两条路径都失效时会要求定位源视频。应用还能读取旧版“仅字幕片段
列表”的 `.vtp`，但再次保存会写成 v2。

## 检查点与取消

检查点默认位于应用状态目录下的 `checkpoints/`，并绑定以下条件：

- 源视频规范路径、文件大小和修改时间；
- 源语言、目标语言、Whisper 模型和翻译提供商；
- 检查点主版本与仍然存在的音频/字幕临时产物。

检查点以私有权限原子写入，在七天后视为过期。正常处理完成后会清除；取消或
崩溃后，下次打开同一视频可选择恢复或重新开始。更改处理设置时旧检查点不会
被误用于新任务。

“取消”表示在安全边界停止并保留已完成阶段，不表示强杀 Python 线程。特别是
标准 Whisper 没有可靠的逐帧取消回调，所以长转写可能延迟响应。导出取消是另
一套机制：它会向正在运行的 FFmpeg 进程发送终止信号，必要时强制结束，并删除
临时输出。

## 隐私与本地数据

| 数据 | 位置或去向 |
| --- | --- |
| 视频、提取音频、Whisper 推理 | 本机；视频/音频不会由本项目上传到翻译提供商 |
| 待翻译字幕文本 | 发送到用户选择及已配置的云端翻译服务 |
| API 密钥 | 操作系统钥匙串、环境变量或当前进程内存 |
| 普通配置、最近文件 | 应用配置目录下 `config.json` |
| 恢复数据 | 应用状态目录下 `checkpoints/`；可能包含转写与译文 |
| Whisper 模型 | 应用缓存目录下 `whisper/`；可由 `VIDEOTRANSLATOR_MODEL_DIR` 覆盖 |
| 翻译缓存 | 应用缓存目录下 `translation-cache.db`；包含原文与译文 |
| 日志 | 应用状态目录下 `logs/`；有敏感信息过滤，但仍应在分享前检查 |
| 临时媒体 | 系统临时目录和应用临时目录 |

云端文本处理还受对应提供商的条款、保留策略和区域设置约束。处理敏感材料前，
请自行确认这些政策。项目不会自动清空 SQLite 翻译缓存；需要彻底清理时，退出
应用后由用户审阅并删除相应本地数据。

应用缓存目录在 Linux 默认为 `${XDG_CACHE_HOME:-~/.cache}/video-translator`，
macOS 为 `~/Library/Caches/VideoTranslator`，Windows 为
`%LOCALAPPDATA%\VideoTranslator\Cache`；可用 `VIDEOTRANSLATOR_CACHE_DIR` 覆盖。
状态目录遵循 `XDG_STATE_HOME`、macOS Application Support 或 Windows
`%LOCALAPPDATA%`，也可用 `VIDEOTRANSLATOR_STATE_DIR` 覆盖。
配置目录遵循 `XDG_CONFIG_HOME`、macOS Application Support 或 Windows
`%APPDATA%`，可用 `VIDEOTRANSLATOR_CONFIG_DIR` 覆盖；检查点还可单独用
`VIDEOTRANSLATOR_CHECKPOINT_DIR` 改变位置。

## 常见问题

### 启动提示找不到 FFmpeg 或 FFprobe

分别运行 `ffmpeg -version` 和 `ffprobe -version`。两者必须来自可用的 FFmpeg
安装并位于当前进程的 `PATH`；只安装 `ffmpeg-python` 不会提供可执行文件。

### 处理时提示缺少 Whisper 或 PyTorch

运行 `python -m pip install -e ".[speech]"`，然后确认当前虚拟环境中
`python -c "import whisper, torch"` 可执行。首次选择模型时 Whisper 可能需要
下载权重。模型不会写入源码树，默认位置及迁移方式见
[模型文件管理](docs/MODEL_FILES_MANAGEMENT.md)。

### 已安装 `python-vlc`，但仍然只有静态画面

Python 绑定无法替代 VLC 原生库。安装与当前 Python 架构匹配的 VLC，或接受静态
预览降级。静态预览仍需要 FFmpeg。

### 翻译结果没有生成

检查设置中的提供商是否与密钥匹配，再检查网络、API 额度、服务区域和目标语言
代码。也可设置相应 `VIDEOTRANSLATOR_*_API_KEY` 后重新启动。应用会把全服务
失败显示为错误，不会静默使用原文冒充译文。

### `.vtp` 打开后提示找不到视频

项目优先使用相对视频路径，所以可整包搬移项目和媒体目录。两条路径都失效时，
选择原视频的新位置即可；字幕片段保存在项目文件
中，不会因为重新定位媒体而丢失。

### 软字幕或烧入失败

先在终端用 FFmpeg 检查源文件。软字幕优先选择 MP4/MOV、MKV 或 WebM；烧入
依赖 FFmpeg 的 `subtitles`/libass 过滤器与系统字体。必要时先将视频转为常见
H.264/AAC MP4，再重试。

### 为什么取消后没有立刻停止

处理线程使用安全边界取消，不会调用 `QThread.terminate()`。Whisper 或正在进行
的媒体阶段返回后才会完成取消；已完成阶段会作为检查点保留。后台视频导出则可
直接终止其 FFmpeg 子进程。

### 钥匙串不可用怎么办

使用环境变量，或在本次会话中输入密钥。应用不会为了持久化而降级到明文 JSON。

## 测试与质量门禁

默认 pytest 配置只收集 `tests/unit/` 中经过审阅的可信测试，并隔离 HOME、Qt
显示后端和钥匙串。历史手工验证脚本默认排除，避免“返回布尔值但 pytest 仍
判定通过”等假阳性。

```bash
# 默认可信门禁
python -m pytest -q

# 查看实际收集项
python -m pytest --collect-only -q

# 仅拒绝会影响正确性的 Ruff 错误（与 CI 一致）
ruff check --select E9,F63,F7,F82 app main.py scripts tests

# 仓库结构检查
python scripts/verify_organization.py

# 可选：生成当前覆盖率报告；项目没有虚构的固定覆盖率承诺
python -m pytest --cov=app --cov-report=term-missing
```

详细测试分层和 legacy opt-in 见 [测试索引](tests/TEST_INDEX.md)。GitHub Actions
在 Python 3.11、无显示 Qt 环境中安装 `.[dev]`，运行 correctness Ruff 子集和
默认 pytest 门禁。CI 定义见
[`.github/workflows/ci.yml`](.github/workflows/ci.yml)。

## 贡献

1. 从当前主分支创建小而明确的分支。
2. 新行为需在默认可信测试集中加入断言；不要新增依赖返回值判断成败的 pytest
   测试，也不要在模块导入阶段永久修改 `sys.modules`。
3. 运行默认 pytest、CI Ruff 命令和结构检查。
4. 修改运行依赖时同步 `pyproject.toml`、`requirements.txt` 和安装文档。
5. 修改数据格式、线程边界或云端数据流时，同步更新架构和隐私说明。

项目使用 [MIT License](LICENSE)。
