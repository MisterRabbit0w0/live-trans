# 构建与发布

## Windows 构建

使用 Windows x64、Python 3.12、Inno Setup 6.7.3。构建环境单独创建，避免将开发环境的 GPU 库、调试工具或本地配置打入产物。

```powershell
python -m venv .venv-build
.venv-build\Scripts\python -m pip install --require-hashes -r packaging\requirements-windows.lock
.venv-build\Scripts\python -m pip install --no-deps --no-build-isolation -e .
.venv-build\Scripts\python scripts\build_windows.py --iscc 'C:\Program Files (x86)\Inno Setup 6\ISCC.exe'
```

没有 Inno Setup 时可使用 `--skip-installer`，只生成便携 ZIP 和单文件 EXE。构建脚本不会启动 LiveTrans，不会录音、下载识别模型或访问翻译服务。

`dist/windows/` 保存最终产物。再次构建前移走这个目录中的旧产物，脚本会拒绝混合新旧版本。`build/frozen/` 是 PyInstaller 中间输出，不用于直接上传 Release。

包内包含 QML、图标、Silero VAD、CPU 推理依赖、Qt QML 插件、许可证和 `build-info.json`。Qt 插件按应用的 QML 导入依赖收集，避免把未使用的可选模块一起带入。构建后读取目录和单文件 EXE 的归档目录，检查资源完整性；该检查不等同于运行验证。

单文件 EXE 内置依赖，需要先解压到临时目录。便携版启动时可直接加载旁边的动态库，日常使用优先选择便携版或安装版。三种形式共用 `%APPDATA%\livetrans` 中的配置。

CPU 发行包不包含 NVIDIA CUDA 库。自动识别模式选择 CPU；需要 CUDA 时从源码安装 `.[cuda]`。模型和 Ollama 不随安装包分发。

## 工作流

| 工作流 | 触发 | 输出 |
|---|---|---|
| CI / `lint.yml` | 分支推送、PR、手动调用、Release 调用 | Ruff、公开文件 / 历史脱敏检查、Gitleaks、离线回归、wheel / sdist |
| Windows packages / `windows.yml` | 手动调用、Release 调用 | ZIP、独立 EXE、安装 EXE、许可证归档、版本和校验清单 |
| Release / `release.yml` | 推送 `v*` 标签 | 检查和构建全部通过后创建 Release 草稿 |

第三方 Actions 固定到完整提交 SHA，由 Dependabot 提醒更新。Gitleaks 与 Inno Setup 下载固定版本并核对 SHA-256。PR 检查仅有仓库读取权限，不接收发布密钥；仅最后创建草稿的任务有 `contents: write` 权限。

Release 使用同一标签下的可复用工作流，不根据另一个分支的历史 CI 成功状态放行。标签必须与 `pyproject.toml` 的 `X.Y.Z` 版本一致；产物集合、Windows 校验清单和构建提交均需匹配。工作流不覆盖同名发布附件。

## 发布步骤

1. 在分支中完成改动，更新 `pyproject.toml` 版本，审查并合入 `main`。
2. 手动运行 `Windows packages`，下载 Actions 产物，按 [界面验收清单](frontend-validation.md) 检查安装、卸载和功能。
3. 在通过检查的提交上创建 `vX.Y.Z` 标签并推送。不要重新指向已经发布的标签。
4. 等待 `Release` 的版本检查、CI 和 Windows 构建完成，下载草稿附件复核版本与 SHA-256。
5. 补充版本说明和已知问题，再手动发布草稿。

当前没有代码签名证书配置，产物为未签名程序。SHA-256 用于检查下载内容一致性，不能替代发布者签名。

## 更新依赖锁

在仓库根目录使用 uv 重新解析 Windows / Python 3.12 依赖：

```powershell
uv pip compile pyproject.toml packaging/requirements-build.in --python-version 3.12 --python-platform windows --generate-hashes --no-emit-index-url --no-emit-find-links --no-header --default-index https://pypi.org/simple -o packaging/requirements-windows.lock
```

检查依赖变更和许可证后，在全新构建环境安装并重新构建。不要把 `pip freeze` 中的本机路径、私有镜像地址或编辑安装路径写进锁文件。

公开的 `.lock` 文件使用自包含的固定版本与哈希列表。项目扫描会拒绝索引、find-links、外部 requirements / constraints、直接 URL、本地路径和 editable 引用；依赖来源通过上面的生成命令指定，不写入锁文件。

## 脱敏与提交

```powershell
python scripts/check_public_tree.py --history
# 明确 git add 文件后检查实际暂存内容
python scripts/check_public_tree.py --staged
```

项目检查只读取 Git 选中的文件，输出路径、行号和规则名，不打印匹配内容。CI 中的 Gitleaks 另行扫描完整可达历史。不要提交配置、密钥、日志、音频样本、缓存、证书或个人绝对路径；测试使用明确的 `example-` / `test-` 占位值。发现历史中有真实密钥时，先撤销或轮换，再单独处理历史，不能只删除当前文件。

## 实现依据

- [PyInstaller spec 与两种打包形式](https://pyinstaller.org/en/stable/spec-files.html)
- [Qt QML 导入扫描工具](https://doc.qt.io/qt-6/qtqml-tooling-qmlimportscanner.html)
- [Inno Setup 非管理员安装](https://jrsoftware.org/ishelp/topic_setup_privilegesrequired.htm)
- [Gitleaks 使用与输出脱敏](https://github.com/gitleaks/gitleaks)
