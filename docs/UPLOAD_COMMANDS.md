# VideoTranslator GitHub 上传命令清单

## 快速上传（推荐方式）

### 1. 使用自动化脚本

```bash
# 运行准备脚本
python scripts/prepare_github_upload.py

# 或者使用批处理脚本 (Windows)
scripts\prepare_github_upload.bat
```

### 2. 手动连接 GitHub

```bash
# 替换 YOUR_USERNAME 为您的 GitHub 用户名
git remote add origin https://github.com/YOUR_USERNAME/VideoTranslator.git
git branch -M main
git push -u origin main
```

## 完整手动步骤

### 准备阶段

```bash
# 1. 进入项目目录
cd d:\Projects\VideoTranslator

# 2. 清理项目文件
# 删除 Python 缓存
Get-ChildItem -Path . -Recurse -Name "__pycache__" | Remove-Item -Recurse -Force
Get-ChildItem -Path . -Recurse -Name "*.pyc" | Remove-Item -Force

# 删除测试缓存
Get-ChildItem -Path . -Recurse -Name ".pytest_cache" | Remove-Item -Recurse -Force

# 清理临时文件
Remove-Item -Path "temp\*" -Force -ErrorAction SilentlyContinue
Remove-Item -Path "logs\*.log" -Force -ErrorAction SilentlyContinue
```

### Git 初始化

```bash
# 3. 初始化 Git 仓库
git init

# 4. 配置 Git 用户信息（如果需要）
git config user.name "Your Name"
git config user.email "your.email@example.com"

# 5. 检查 .gitignore 文件
type .gitignore
```

### 添加文件并提交

```bash
# 6. 添加所有文件
git add .

# 7. 检查状态
git status

# 8. 查看即将提交的文件
git diff --cached --name-only

# 9. 创建初始提交
git commit -m "Initial commit: VideoTranslator - 智能视频翻译系统

Features:
- 基于 PyQt5 的桌面应用程序
- 集成 OpenAI Whisper 语音识别
- 支持多种翻译 API（OpenAI、DeepL、Google）
- 可视化字幕编辑器
- 视频导出功能（硬字幕/软字幕）
- 完整的测试套件
- 系统健康检查和内存管理"
```

### 连接 GitHub

```bash
# 10. 在 GitHub 上创建新仓库
# 访问 https://github.com/new
# 仓库名称: VideoTranslator
# 描述: 智能视频翻译系统 - 基于 PyQt5 和 OpenAI Whisper
# 选择 Public 或 Private
# 不要勾选 "Initialize with README"

# 11. 连接远程仓库
git remote add origin https://github.com/YOUR_USERNAME/VideoTranslator.git

# 12. 验证远程仓库
git remote -v

# 13. 设置主分支
git branch -M main

# 14. 推送到 GitHub
git push -u origin main
```

## 身份验证解决方案

### 方案 1: Personal Access Token

```bash
# 推送时输入：
# Username: your_github_username
# Password: your_personal_access_token (不是密码)
```

如何创建 Personal Access Token：
1. 访问 GitHub Settings > Developer settings > Personal access tokens
2. 点击 "Generate new token"
3. 勾选 "repo" 权限
4. 复制生成的 token

### 方案 2: SSH 密钥

```bash
# 生成 SSH 密钥
ssh-keygen -t rsa -b 4096 -C "your.email@example.com"

# 添加到 ssh-agent
ssh-add ~/.ssh/id_rsa

# 复制公钥到 GitHub
cat ~/.ssh/id_rsa.pub
# 在 GitHub Settings > SSH and GPG keys 中添加

# 更改远程仓库 URL
git remote set-url origin git@github.com:YOUR_USERNAME/VideoTranslator.git
```

## 常见问题解决

### 文件过大

```bash
# 检查大文件
git ls-files | xargs ls -la | sort -k5 -n

# 如果有大文件被意外添加，从 Git 中移除
git rm --cached path/to/large/file
git commit -m "Remove large file from tracking"
```

### 推送失败

```bash
# 如果推送失败，可能需要先拉取
git pull origin main --allow-unrelated-histories

# 或者强制推送（谨慎使用）
git push -f origin main
```

### 分支名称问题

```bash
# 如果默认分支是 master，改为 main
git branch -M main
git push -u origin main
```

## 后续维护

### 日常提交

```bash
# 1. 检查状态
git status

# 2. 添加更改
git add .

# 3. 提交
git commit -m "描述你的更改"

# 4. 推送
git push
```

### 版本标记

```bash
# 创建版本标签
git tag -a v1.0.0 -m "Version 1.0.0 - 首次发布"
git push origin v1.0.0
```

### 分支管理

```bash
# 创建新分支
git checkout -b feature/new-feature

# 切换分支
git checkout main

# 合并分支
git merge feature/new-feature

# 删除分支
git branch -d feature/new-feature
```

## 验证上传成功

访问您的 GitHub 仓库页面，检查：
- [ ] 所有文件都已上传
- [ ] README.md 正确显示
- [ ] .gitignore 正确忽略了不需要的文件
- [ ] 模型文件被正确忽略
- [ ] 项目描述完整
- [ ] 许可证文件存在

## 优化建议

1. **设置分支保护**: 在 GitHub 仓库设置中启用分支保护规则
2. **启用 Issues**: 用于跟踪问题和功能请求
3. **创建 Wiki**: 添加更详细的文档
4. **设置 GitHub Actions**: 自动化测试和构建
5. **添加贡献指南**: 创建 CONTRIBUTING.md 文件

---

**注意**: 请将 `YOUR_USERNAME` 替换为您的实际 GitHub 用户名。
