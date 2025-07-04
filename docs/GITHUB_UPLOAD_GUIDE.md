# GitHub 上传指南

## 📋 准备工作

### 1. 检查项目状态
确保您的项目已经完成开发并且可以正常运行：

```bash
# 测试项目是否正常运行
python main.py

# 运行测试套件
python -m pytest tests/ -v
```

### 2. 清理项目文件
运行清理脚本移除不必要的文件：

```bash
# 清理缓存文件
Get-ChildItem -Path . -Recurse -Name "__pycache__" | Remove-Item -Recurse -Force
Get-ChildItem -Path . -Recurse -Name "*.pyc" | Remove-Item -Force
Get-ChildItem -Path . -Recurse -Name ".pytest_cache" | Remove-Item -Recurse -Force

# 清理临时文件
Remove-Item -Path "temp\*" -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -Path "logs\*.log" -Force -ErrorAction SilentlyContinue
```

## 🚀 GitHub 上传步骤

### 步骤 1: 创建 GitHub 仓库

1. 登录 [GitHub](https://github.com)
2. 点击右上角的 "+" 按钮，选择 "New repository"
3. 填写仓库信息：
   - **Repository name**: `VideoTranslator`
   - **Description**: `智能视频翻译系统 - 基于 PyQt5 和 OpenAI Whisper 的桌面应用程序`
   - **Visibility**: 选择 Public 或 Private
   - **不要勾选** "Initialize this repository with a README"（因为我们已经有 README.md）
4. 点击 "Create repository"

### 步骤 2: 初始化本地 Git 仓库

在项目根目录打开 PowerShell 或命令提示符：

```bash
# 初始化 Git 仓库
git init

# 设置用户信息（如果还没有设置）
git config user.name "Your Name"
git config user.email "your.email@example.com"

# 检查 Git 状态
git status
```

### 步骤 3: 配置 .gitignore

项目已经包含了 `.gitignore` 文件，其中包含了以下重要配置：

**Model 文件策略**：
- ✅ 保留小型模型（tiny, base, small）
- ❌ 忽略大型模型文件（medium, large）
- ❌ 忽略 .pt 和 .pth 模型文件

**其他忽略文件**：
- Python 缓存文件
- 虚拟环境
- IDE 配置文件
- 日志文件
- 临时文件
- 媒体文件（可选）

### 步骤 4: 添加文件到 Git

```bash
# 添加所有文件到暂存区
git add .

# 检查暂存区状态
git status

# 如果需要，可以查看将要提交的文件
git diff --cached --name-only
```

### 步骤 5: 创建初始提交

```bash
# 创建初始提交
git commit -m "Initial commit: VideoTranslator - 智能视频翻译系统

Features:
- 基于 PyQt5 的桌面应用程序
- 集成 OpenAI Whisper 语音识别
- 支持多种翻译 API（OpenAI、DeepL、Google）
- 可视化字幕编辑器
- 视频导出功能（硬字幕/软字幕）
- 完整的测试套件（51个测试文件）
- 系统健康检查和内存管理"
```

### 步骤 6: 连接到 GitHub 远程仓库

```bash
# 添加远程仓库（替换 YOUR_USERNAME 为您的 GitHub 用户名）
git remote add origin https://github.com/YOUR_USERNAME/VideoTranslator.git

# 验证远程仓库
git remote -v
```

### 步骤 7: 推送到 GitHub

```bash
# 推送到 GitHub（首次推送）
git push -u origin main

# 如果遇到默认分支名称问题，可能需要先设置分支
git branch -M main
git push -u origin main
```

## 🔧 处理常见问题

### 问题 1: 身份验证失败

如果推送时提示身份验证错误：

**解决方案 1: 使用 Personal Access Token**
1. 进入 GitHub Settings > Developer settings > Personal access tokens
2. 生成新的 token，勾选 `repo` 权限
3. 使用 token 代替密码：
```bash
git push -u origin main
# Username: your_username
# Password: your_personal_access_token
```

**解决方案 2: 使用 SSH**
```bash
# 生成 SSH 密钥
ssh-keygen -t rsa -b 4096 -C "your.email@example.com"

# 添加到 GitHub（复制公钥内容到 GitHub Settings > SSH keys）
cat ~/.ssh/id_rsa.pub

# 更改远程仓库 URL
git remote set-url origin git@github.com:YOUR_USERNAME/VideoTranslator.git
```

### 问题 2: 文件过大

如果遇到文件过大错误：

```bash
# 检查大文件
git ls-files | xargs du -sh | sort -h

# 从 Git 中移除大文件
git filter-branch --force --index-filter "git rm --cached --ignore-unmatch path/to/large/file" --prune-empty --tag-name-filter cat -- --all

# 或者使用 BFG Repo-Cleaner
# 先安装 BFG: https://rtyley.github.io/bfg-repo-cleaner/
# java -jar bfg.jar --strip-blobs-bigger-than 100M .
```

### 问题 3: Model 文件管理

**如果需要上传小型模型文件**：
```bash
# 强制添加特定的小型模型文件
git add -f model/whisper/tiny.pt
git add -f model/whisper/base.pt
git commit -m "Add small Whisper models"
```

**如果要完全忽略所有模型文件**：
修改 `.gitignore`：
```gitignore
# 忽略所有模型文件
model/whisper/*.pt
model/whisper/*.pth
model/whisper/*
!model/whisper/.gitignore
```

## 📝 完善 GitHub 仓库

### 1. 添加 LICENSE 文件

```bash
# 创建 MIT 许可证文件
```

### 2. 完善 README.md

确保 README.md 包含：
- 项目描述
- 安装说明
- 使用方法
- 贡献指南
- 许可证信息

### 3. 创建 Issues 模板

在 `.github/ISSUE_TEMPLATE/` 目录下创建问题模板。

### 4. 添加 GitHub Actions（可选）

创建 `.github/workflows/ci.yml` 用于自动化测试。

## 🎯 发布策略

### 创建第一个 Release

1. 在 GitHub 仓库页面点击 "Releases"
2. 点击 "Create a new release"
3. 填写版本信息：
   - **Tag version**: `v1.0.0`
   - **Release title**: `VideoTranslator v1.0.0 - 首次发布`
   - **Description**: 详细描述功能特性

### 版本标记

```bash
# 创建版本标签
git tag -a v1.0.0 -m "VideoTranslator v1.0.0 - 首次发布"
git push origin v1.0.0
```

## 📊 维护指南

### 日常提交工作流

```bash
# 1. 拉取最新代码
git pull origin main

# 2. 创建功能分支
git checkout -b feature/new-feature

# 3. 进行开发和测试
# ... 开发工作 ...

# 4. 提交更改
git add .
git commit -m "Add new feature: description"

# 5. 推送分支
git push origin feature/new-feature

# 6. 创建 Pull Request
```

### 定期维护

```bash
# 清理本地分支
git branch -d feature/completed-feature

# 清理远程跟踪分支
git remote prune origin

# 压缩提交历史（如果需要）
git rebase -i HEAD~3
```

## ⚠️ 注意事项

1. **敏感信息**: 确保 API 密钥等敏感信息不会被提交
2. **大文件**: Whisper 模型文件较大，建议使用 Git LFS 或提供下载说明
3. **依赖管理**: 确保 `requirements.txt` 文件是最新的
4. **文档更新**: 及时更新 README.md 和其他文档
5. **测试**: 提交前运行完整的测试套件

## 🔗 有用链接

- [GitHub 官方文档](https://docs.github.com/)
- [Git 教程](https://git-scm.com/docs)
- [GitHub CLI 工具](https://cli.github.com/)
- [Git LFS 使用指南](https://git-lfs.github.io/)

---

**提示**: 如果您是第一次使用 Git 和 GitHub，建议先在测试仓库中练习这些步骤。
