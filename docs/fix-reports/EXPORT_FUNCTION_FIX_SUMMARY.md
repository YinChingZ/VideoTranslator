# VideoTranslator 字幕导出功能修复总结

## 问题描述
VideoTranslator应用中，导出对话框的"将字幕嵌入视频"（软字幕）和"烧入字幕（硬字幕）"选项不能正常工作，只能导出字幕文件。

## 修复内容

### 1. 修复了导出对话框路径显示问题
**文件**: `app/gui/export_dialog.py`
**问题**: 输出路径是Path对象，调用setText时引发TypeError
**修复**: 添加了稳健的路径到字符串转换

```python
def update_output_path(self):
    """更新输出路径显示"""
    if not self.video_path:
        return
    # 其他代码...
    # 确保路径是字符串格式
    path_str = str(output_path) if not isinstance(output_path, str) else output_path
    self.output_path_edit.setText(path_str)
```

### 2. 添加了视频处理功能
**文件**: `app/core/video.py`
**新增方法**:
- `embed_subtitles_to_video()`: 嵌入软字幕到视频
- `burn_subtitles_to_video()`: 烧入硬字幕到视频

**关键修复**: 解决了ffmpeg-python过滤器图错误，通过正确分离视频流和音频流：

```python
# 修复前（错误）：
video = ffmpeg.input(video_path)
out = ffmpeg.output(video, video.audio, output_path)  # 导致 "multiple outgoing edges" 错误

# 修复后（正确）：
input_video = ffmpeg.input(video_path)
video_stream = input_video.video
audio_stream = input_video.audio
video_with_subs = video_stream.filter('subtitles', subtitle_path)
out = ffmpeg.output(video_with_subs, audio_stream, output_path)
```

### 3. 重构了主窗口导出逻辑
**文件**: `app/gui/main_window.py`
**修改**: 重构了`show_export_dialog()`方法，添加了分支逻辑：

```python
# 根据导出选项决定处理方式
if export_options.get("embed_subtitles", False) or export_options.get("hardcode_subtitles", False):
    # 导出视频（嵌入或烧入字幕）
    self._export_video_with_subtitles(processor, export_options, dialog)
else:
    # 仅导出字幕文件
    self._export_subtitle_file(processor, export_options, dialog)
```

**新增方法**:
- `_export_subtitle_file()`: 处理纯字幕文件导出
- `_export_video_with_subtitles()`: 处理视频导出（软字幕/硬字幕）

## 技术细节

### 软字幕嵌入 (embed_subtitles_to_video)
- 使用ffmpeg将字幕作为字幕轨道添加到视频容器中
- 视频和音频流使用`copy`编码器，避免重新编码损失
- 字幕使用`mov_text`编码器，确保MP4兼容性

### 硬字幕烧入 (burn_subtitles_to_video)
- 使用ffmpeg的`subtitles`或`ass`滤镜将字幕渲染到视频画面上
- 支持多种字幕格式（SRT, ASS等）
- 视频需要重新编码（使用libx264），音频保持原样

### 错误处理
- 文件存在性检查
- FFmpeg可用性检查
- 详细的错误日志记录
- 临时文件清理

## 测试验证

创建了多个测试脚本验证修复：

1. **test_burn_subtitles_fix.py**: 测试硬字幕烧入功能
2. **test_embed_subtitles.py**: 测试软字幕嵌入功能  
3. **test_full_export.py**: 综合测试所有导出功能

### 测试结果
```
✅ FFmpeg 集成完成
✅ 软字幕嵌入功能已实现
✅ 硬字幕烧入功能已实现（修复了ffmpeg-python过滤器图错误）
✅ 导出对话框UI支持
✅ 主窗口导出逻辑分支
✅ 参数验证和错误处理
```

## 使用方法

1. 在应用中打开视频文件
2. 生成或导入字幕
3. 点击导出按钮
4. 在导出对话框中选择选项：
   - **"将字幕嵌入视频"**: 创建带软字幕的视频（可以开关字幕）
   - **"烧入字幕（硬字幕）"**: 创建硬字幕视频（字幕永久显示）
   - **默认**: 仅导出字幕文件
5. 点击确定开始导出

## 依赖要求

- FFmpeg必须安装并在系统PATH中可用
- Python包：`ffmpeg-python`

## 注意事项

1. 软字幕嵌入速度较快，因为不需要重新编码视频
2. 硬字幕烧入需要重新编码视频，速度较慢但兼容性更好
3. 导出过程中会创建临时字幕文件，完成后自动清理
4. 支持多种字幕格式：SRT, ASS, VTT等

## 修复完成日期
2025年7月3日

## 状态
✅ 完成 - 所有导出功能现在都能正常工作
