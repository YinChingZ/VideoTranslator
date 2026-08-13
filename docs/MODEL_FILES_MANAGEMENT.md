# Whisper 模型文件管理

VideoTranslator 不在 Git 仓库或安装包中分发 Whisper 权重。首次使用某个模型时，
`openai-whisper` 会下载权重到应用的用户可写缓存；后续启动复用同一文件。这样既
避免数 GB 文件污染 Git 历史，也允许应用安装在只读位置。

## 存储位置

应用通过 `app.utils.paths.get_whisper_model_dir()` 选择目录，优先级如下：

1. `VIDEOTRANSLATOR_MODEL_DIR` 指定的完整目录；
2. 应用缓存目录下的 `whisper/`。

应用缓存目录为：

| 平台 | 默认目录 |
| --- | --- |
| Linux | `${XDG_CACHE_HOME:-~/.cache}/video-translator` |
| macOS | `~/Library/Caches/VideoTranslator` |
| Windows | `%LOCALAPPDATA%\VideoTranslator\Cache` |

设置了 `VIDEOTRANSLATOR_CACHE_DIR` 时，它会取代整套应用缓存目录；专用的
`VIDEOTRANSLATOR_MODEL_DIR` 优先级更高。程序会创建目录并在支持 POSIX 权限的
文件系统上尽量设为仅当前用户可访问。

例如把大型权重放到独立磁盘：

```bash
# macOS / Linux
export VIDEOTRANSLATOR_MODEL_DIR="/Volumes/Models/VideoTranslator/whisper"
video-translator
```

```powershell
# Windows PowerShell
$env:VIDEOTRANSLATOR_MODEL_DIR = "D:\Models\VideoTranslator\whisper"
video-translator
```

## 下载与预热

正常方式是在应用设置中选择模型并开始处理；`SpeechRecognizer` 会把下载目录显式
传给 Whisper。若要在部署前预热缓存，请使用项目的路径解析器，避免 Whisper 的
独立默认目录与应用目录不一致：

```bash
python -c "from app.utils.paths import ensure_private_directory,get_whisper_model_dir; import whisper; p=ensure_private_directory(get_whisper_model_dir()); whisper.load_model('base', download_root=str(p))"
```

下载需要网络与足够磁盘空间。模型越大通常准确率越高，但启动、推理、内存和磁盘
成本也更高；默认 `base` 是较轻的通用起点。实际可用模型名称以当前设置界面和所
安装的 `openai-whisper` 版本为准。

## 迁移和清理

退出应用后，可把整个 `whisper/` 目录移动到新位置，再设置
`VIDEOTRANSLATOR_MODEL_DIR` 指向它。不要在运行中移动正在读取的权重。

清理时只删除上表解析出的模型目录。删除不会影响项目或字幕，但下次使用相应模型
会重新下载。应用不会自动删除模型，因为下载成本高且用户可能在多个会话中复用。

## 仓库与发布规则

- 不要把 `.pt`、`.pth` 或模型缓存强制加入 Git；`.gitignore` 已排除这些文件。
- 不要把缓存目录放在源码树中，也不要用 Git LFS 分发第三方权重。
- 构建 wheel、运行默认测试和编辑既有项目都不需要模型文件。
- 完整转写环境需安装 `speech` extra：`python -m pip install -e ".[speech]"`。
- 离线部署应在获准的环境预热应用缓存，并遵守模型来源的许可证和分发条款。
