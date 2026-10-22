# Changelog

本文件遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循[语义化版本](https://semver.org/lang/zh-CN/)。条目由
release-please 根据 Conventional Commits 自动汇总，勿手工编辑已发布段落。

## [0.2.1](https://github.com/MisterRabbit0w0/live-trans/compare/v0.2.0...v0.2.1) (2026-10-22)


### Features

* add cross-platform audio backends and out-of-process model worker ([d7348a1](https://github.com/MisterRabbit0w0/live-trans/commit/d7348a174dbf60691e6e7cb185256ef4afd9a0c5))
* **desktop:** 记录页相对时间显示与纪要异步状态流 ([c91d52d](https://github.com/MisterRabbit0w0/live-trans/commit/c91d52decfa925382fadc5941e3c7da7fd09c514))
* split session into transcriber/translation stages and add transcript recording ([1dd8c70](https://github.com/MisterRabbit0w0/live-trans/commit/1dd8c708d8b6dc5e0fe124531007df84734858fc))
* **ui:** add QML control center and serialized runtime ([27c9871](https://github.com/MisterRabbit0w0/live-trans/commit/27c9871e30a45e319afa4dd13266a3153e48e557))


### Bug Fixes

* **audio:** correct process loopback Windows requirement ([017226e](https://github.com/MisterRabbit0w0/live-trans/commit/017226eb0a7e49b90c192cc9ba3723d91e5c4d3e))
* **build:** 修复冻结烟测两处死循环/误杀缺陷 ([335d482](https://github.com/MisterRabbit0w0/live-trans/commit/335d482909ec101e69530c959c1bb239f92c0722))
* **build:** 冻结烟测默认超时提至 120s，覆盖 CI 冷机引导 ([5a35998](https://github.com/MisterRabbit0w0/live-trans/commit/5a35998200792eddb0cdb40f057f6b72f4ed959a))
* **build:** 移除 PyInstaller 中遗留的 QML 依赖与 hook，修复 Windows 打包 ([8e06436](https://github.com/MisterRabbit0w0/live-trans/commit/8e06436c49541f95ea6ad34660ae7fcf082ac2b6))
* clarify overview and prevent duplicate instances ([6ee1a96](https://github.com/MisterRabbit0w0/live-trans/commit/6ee1a960378e329aee0c8ffcc31bf4eba154ace7))
* clear font recovery after successful save ([76e9432](https://github.com/MisterRabbit0w0/live-trans/commit/76e9432ace41530748137e67ab0d2657819df0c5))
* **deps:** @tauri-apps/api 回退 2.11.1 与 tauri crate 对齐 ([#20](https://github.com/MisterRabbit0w0/live-trans/issues/20)) ([a41466b](https://github.com/MisterRabbit0w0/live-trans/commit/a41466b0d6b6005afc0bf08bed645758a5405af6))
* harden qml packaging compatibility ([c895cfc](https://github.com/MisterRabbit0w0/live-trans/commit/c895cfc80c5d37c8a7f4d50720cc185812c1ea15))
* harden remaining runtime and settings paths ([fb973e2](https://github.com/MisterRabbit0w0/live-trans/commit/fb973e2fae7a33017f865be32ab896a8c154ad74))
* harden shutdown and release validation ([a005fbe](https://github.com/MisterRabbit0w0/live-trans/commit/a005fbeee8ae4de3d24632d7484433d5e8ef1040))
* **records:** 纪要异步任务、配置快照、内容绑定缓存与预算/截断保护 ([4d2c201](https://github.com/MisterRabbit0w0/live-trans/commit/4d2c20108df645909a71f96f4cd78b3d7f9db048))
* **release:** audit dependency lock sources and paths ([c23119d](https://github.com/MisterRabbit0w0/live-trans/commit/c23119d610b98cca5bfba2484c17ff5fdfc75450))
* **security:** 放行占位用户名路径，修复历史审计误报 ([f526119](https://github.com/MisterRabbit0w0/live-trans/commit/f5261195829f8b163b8ede9253eccbdf0cdefa69))
* serialize deferred runtime cleanup ([957763a](https://github.com/MisterRabbit0w0/live-trans/commit/957763af0e3f2b37aeb95040893add659afe964e))
* **session:** 正常停止排空尾句与在途工作，结果绑定采集时记录文件 ([6b32f85](https://github.com/MisterRabbit0w0/live-trans/commit/6b32f85d896bc784406491d969c3b67448bb1df7))
* **style:** 格式化 packaging/icon.py 保证单行不超过 100 字符 ([b154e53](https://github.com/MisterRabbit0w0/live-trans/commit/b154e534d2c1d6791f00dc8a38ca002358ad1b69))
* **translate:** preserve Chinese script conversion ([7d3c571](https://github.com/MisterRabbit0w0/live-trans/commit/7d3c5711e9e24ba95cddf8b66ef903652972e370))
* **worker:** hello 握手前不再阻塞于 numpy 导入 ([b66eb67](https://github.com/MisterRabbit0w0/live-trans/commit/b66eb67c7f3a58556cf1fbbc918b94fd4f37e06d))
* **worker:** hello 握手前去重依赖 + 启动路径探针诊断 ([0bd82eb](https://github.com/MisterRabbit0w0/live-trans/commit/0bd82ebab84be6ee92dfbc66882c3966711faf70))


### Documentation

* 发行链与验收文档对齐 NSIS 现实，CHANGELOG 记录 0.2.0 ([731f059](https://github.com/MisterRabbit0w0/live-trans/commit/731f0593d01d00c242f137d55f7ca984795b1889))
* 更新 README 为 Tauri 架构、解耦流水线与 Mermaid 架构图 ([622b130](https://github.com/MisterRabbit0w0/live-trans/commit/622b13000b93243ce6955e0878a4f7b66b905dca))

## [0.2.0] - 2026-10-10

### 修复

- **纪要可靠性与响应**：纪要生成移出核心事件循环，改为有界异步任务（单飞 + 完成事件 + 状态查询/取消）；提交时绑定当前配置快照；缓存按源内容哈希、模型、服务身份与提示词版本校验并原子写入，写失败上报；新增输入预算（`record.summary_max_chars`，默认 12 万字符）与截断/空输出判定，不再把不完整结果当作完整纪要。
- **记录与导出时间**：记录页、复制文本、纪要与 Markdown 导出统一以会话起点换算会内时间，不再把 Unix 绝对时间误当分钟。
- **正常停止数据完整性**：停止时先排空 VAD 尾段与在途识别/翻译（5 秒预算，超时降级为中止）；热切记录后迟到结果按采集时归属处理，不串入新文件。

### 发行与工程

- **桌面发行链**：发行物改为 Tauri NSIS 安装器 + 便携 ZIP，随包 `livetrans-core` onedir（冻结核心改 console 构建并保留管道通信）；移除 Inno Setup、独立单文件 EXE 与 PySide6 构建依赖。
- **发行路径安全**：release 构建不再回退构建机路径与环境变量；缺失随包核心时给出明确错误。
- **发行布局检查**：构建链静态核对安装/便携布局，并扫描壳二进制中的构建机路径残留（`check_release_layout.py`）。
- **三端 CI**：CI 增加 Vitest、svelte-check、vite 生产构建与 cargo test/clippy；保留 Python、脱敏与打包检查。
- **版本单一来源**：`bump_version.py` 以 `pyproject.toml` 同步四处清单，CI 与标签校验强制一致。
- **CHANGELOG 自动化**：接入 release-please。
- **文档对齐**：发布、验收与 README 按现行发行链重写。

## [0.1.0] - 未发布

- 首个里程碑版本：迁移至 Tauri + Svelte 桌面壳与冻结 Python 核心的开发中状态，占位待首次发布。
