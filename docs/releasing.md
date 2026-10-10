# 构建与发布

## Windows 构建

使用 Windows x64、Python 3.12、Node.js 24 与稳定版 Rust 工具链。构建环境单独创建，避免将开发环境的 GPU 库、调试工具或本地配置打入产物。首次构建 Tauri 安装器时 CLI 会联网下载 NSIS（内置哈希校验）。

```powershell
python -m venv .venv-build
.venv-build\Scripts\python -m pip install --require-hashes -r packaging\requirements-windows.lock
.venv-build\Scripts\python -m pip install --no-deps --no-build-isolation -e .
npm ci --prefix desktop
.venv-build\Scripts\python scripts\build_windows.py
```

`build_windows.py` 依次执行：PyInstaller 冻结 `livetrans-core` onedir → `check_windows_package.py` 资源完整性检查 → 复制核心到 `desktop/src-tauri/resources/livetrans-core/` → `tauri build --bundles nsis` → 便携布局组装与 `check_release_layout.py` 静态检查（布局 + 壳二进制路径残留扫描）→ ZIP、许可证归档、`build-info.json` 与 `SHA256SUMS.txt`。加 `--skip-installer` 时 Tauri 以 `--no-bundle` 编译，只产出便携 ZIP，不生成安装器。构建脚本不启动冻结核心或壳，不会录音、下载识别模型或访问翻译服务。

`dist/windows/` 保存最终产物，再次构建前移走旧产物（脚本拒绝混合新旧版本）：

| 产物 | 说明 |
|---|---|
| `LiveTrans-{version}-windows-x64-setup.exe` | Tauri NSIS 安装器，普通用户安装 |
| `LiveTrans-{version}-windows-x64-portable.zip` | 便携版，解压即用 |
| `third-party-licenses.zip` | 许可证归档 |
| `build-info.json` / `SHA256SUMS.txt` | 构建信息与校验清单 |

两种发行形式内部布局一致：壳 `livetrans.exe` 旁边是 `livetrans-core/`（PyInstaller onedir，含 `livetrans-core.exe` 与 `_internal/`）、`licenses/` 与 `build-info.json`。`build/frozen/` 与 `desktop/src-tauri/resources/` 是中间目录，不直接上传 Release；后者由 `check_bundled_core.py` 护栏保证手工 `tauri build` 时核心已就位。

发行物包含冻结 Python 核心、Silero VAD、CPU 推理依赖、图标与许可证。图标 ICO 已提交在 `desktop/src-tauri/icons/`，构建不再需要 Qt/PySide6。冻结核心以 `console=True` 构建，由壳与 worker 的 `CREATE_NO_WINDOW` 隐藏控制台；壳在 release 下只认随包 `livetrans-core/livetrans-core.exe`，缺失时给出明确错误，不回退构建机路径。安装版与便携版共用 `%APPDATA%\livetrans` 中的配置。

CPU 发行包不包含 NVIDIA CUDA 库。自动识别模式选择 CPU；需要 CUDA 时从源码安装 `.[cuda]`。模型和 Ollama 不随安装包分发。

## 工作流

| 工作流 | 触发 | 输出 |
|---|---|---|
| CI / `lint.yml` | 分支推送、PR、手动调用、Release 调用 | Ruff、版本一致性（`bump_version.py --check`）、公开文件 / 历史脱敏检查、Gitleaks、离线回归、wheel / sdist、Vitest / svelte-check / vite build、cargo test / clippy |
| Windows packages / `windows.yml` | 手动调用、Release 调用 | NSIS 安装器、便携 ZIP、许可证归档、版本和校验清单（构建内含发行布局静态检查） |
| Release / `release.yml` | 推送 `v*` 标签 | 检查和构建全部通过后创建 Release 草稿 |
| Release Please / `release-please.yml` | 推送 `main`、手动调用 | 按 Conventional Commits 维护版本 / CHANGELOG PR |

第三方 Actions 固定到完整提交 SHA，由 Dependabot（github-actions / npm / cargo / pip）提醒更新。Gitleaks 下载固定版本并核对 SHA-256。PR 检查仅有仓库读取权限，不接收发布密钥；仅最后创建草稿的任务有 `contents: write` 权限。

Release 使用同一标签下的可复用工作流，不根据另一个分支的历史 CI 成功状态放行。标签与四处清单（`pyproject.toml`、`desktop/package.json`、`desktop/src-tauri/tauri.conf.json`、`desktop/src-tauri/Cargo.toml`）版本必须一致，由 `release_artifacts.py --validate-tag` 在发布前强制校验；产物集合、Windows 校验清单和构建提交均需匹配。工作流不覆盖同名发布附件。

## 版本管理

`pyproject.toml` 是版本唯一来源。`scripts/bump_version.py X.Y.Z` 同步四处清单，`--check` 校验漂移（CI 每提交执行）。日常提交遵循 Conventional Commits 后，release-please 自动维护版本 PR 与 `CHANGELOG.md`。

1.0 之前 minor 版本对应路线图主题（0.2 能交付、0.3 低延迟……），只在该主题达到完成标准时升级。因此 release-please 配置为 1.0 前 `feat` 只升 patch、破坏性变更只升 minor；进入下一主题时在合入提交正文加 `Release-As: 0.X.0` 脚注显式指定。release-please 以最近的版本标签为起点汇总提交，当前版本未打标签时生成的版本 PR 会把更早的提交重复计入，不应合入。

## 发布步骤

1. 在分支中完成改动并合入 `main`。合入后 `release-please.yml` 工作流会根据 Conventional Commits 自动维护版本 PR（更新 `pyproject.toml`、桌面与 Rust 清单及 `CHANGELOG.md`）；审查并合入该 PR 得到待发布版本。首个通过验收的版本（当前为 0.2.0，清单已就位）跳过这一步，直接从第 2 步开始。
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

- [PyInstaller spec 与打包形式](https://pyinstaller.org/en/stable/spec-files.html)
- [Tauri 打包配置](https://v2.tauri.app/reference/config/)
- [Tauri NSIS 打包器](https://v2.tauri.app/distribute/windows-installer/)
- [Gitleaks 使用与输出脱敏](https://github.com/gitleaks/gitleaks)
