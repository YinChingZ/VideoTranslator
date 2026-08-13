# GitHub 发布与协作指南

本项目已经是 Git 仓库，并包含自动化测试、打包元数据、许可证和 README。不要
重新运行 `git init`，也不要把 API 密钥、媒体、缓存或 Whisper 权重加入版本库。

## 提交前检查

在项目虚拟环境中执行：

```bash
python -m ruff check app main.py scripts tests
python -m pytest -q
python -m compileall -q app main.py scripts
python scripts/verify_organization.py
python -m build --wheel
```

随后只读检查即将提交的内容：

```bash
git status --short
git diff --check
git diff --stat
git diff
```

特别确认：

- 配置 JSON、`.env`、日志、缓存、临时媒体和 API 密钥没有进入变更；
- `.pt`、`.pth` 和应用模型缓存没有被强制加入；
- 测试没有依赖真实用户目录、真实钥匙串或生产 API；
- README、架构和测试索引与行为变更同步。

## 分支与 Pull Request

使用主题分支提交一个内聚变更：

```bash
git switch -c fix/short-description
git add path/to/intended-file another/intended-file
git diff --cached
git commit -m "fix: describe the user-visible outcome"
git push -u origin fix/short-description
```

然后在 GitHub 创建 Pull Request，说明问题、行为变化、验证命令和仍存在的边界。
等待仓库 CI 通过并处理审查意见后再合并。不要为了绕过分支保护或失败检查使用
强制推送。

若仓库尚未配置远程，先在 GitHub 创建空仓库，再执行一次：

```bash
git remote add origin https://github.com/OWNER/VideoTranslator.git
git push -u origin HEAD
```

认证优先使用 GitHub CLI、系统凭据管理器或 SSH 密钥；不要把访问令牌写入远程
URL、脚本、配置文件或终端历史。

## 版本发布

发布前更新版本与变更说明，确认 wheel 可以在干净环境安装，再创建带注释标签：

```bash
git tag -a v2.0.0 -m "VideoTranslator 2.0.0"
git push origin v2.0.0
```

版本号只是示例；必须与 `pyproject.toml` 及应用版本保持一致。GitHub Release 应
附构建产物的来源和校验信息，不附模型权重或用户数据。

## 大文件和敏感数据误提交

如果文件尚未提交，用普通取消暂存和 `.gitignore` 修正即可；如果已经推送，不要
照搬会重写所有历史的命令。立即撤销凭据、停止继续传播，再与仓库维护者确认受
影响的分支和历史清理方案。历史改写会影响所有协作者，必须单独评审和协调。

Whisper 模型的合法位置与离线预热方式见
[模型文件管理](MODEL_FILES_MANAGEMENT.md)。
