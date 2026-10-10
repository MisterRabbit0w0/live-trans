# Changelog

本文件遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循[语义化版本](https://semver.org/lang/zh-CN/)。条目由
release-please 根据 Conventional Commits 自动汇总，勿手工编辑已发布段落。

## [0.3.0](https://github.com/MisterRabbit0w0/live-trans/compare/v0.2.0...v0.3.0) (2026-10-10)


### Features

* add cross-platform audio backends and out-of-process model worker ([d7348a1](https://github.com/MisterRabbit0w0/live-trans/commit/d7348a174dbf60691e6e7cb185256ef4afd9a0c5))
* **desktop:** 记录页相对时间显示与纪要异步状态流 (FIX-006) ([2332f9e](https://github.com/MisterRabbit0w0/live-trans/commit/2332f9e2668498589e6f0c8b080d042b5685868f))
* split session into transcriber/translation stages and add transcript recording ([1dd8c70](https://github.com/MisterRabbit0w0/live-trans/commit/1dd8c708d8b6dc5e0fe124531007df84734858fc))
* **ui:** add QML control center and serialized runtime ([27c9871](https://github.com/MisterRabbit0w0/live-trans/commit/27c9871e30a45e319afa4dd13266a3153e48e557))


### Bug Fixes

* **audio:** correct process loopback Windows requirement ([017226e](https://github.com/MisterRabbit0w0/live-trans/commit/017226eb0a7e49b90c192cc9ba3723d91e5c4d3e))
* **build:** 修复冻结烟测两处死循环/误杀缺陷 ([5d7c933](https://github.com/MisterRabbit0w0/live-trans/commit/5d7c933a083dc25498aeed921d712cdb90cb8a92))
* **build:** 冻结烟测默认超时提至 120s，覆盖 CI 冷机引导 ([2f48acd](https://github.com/MisterRabbit0w0/live-trans/commit/2f48acd45f7e18b0f472a1e621ea30b307b472f6))
* **build:** 移除 PyInstaller 中遗留的 QML 依赖与 hook，修复 Windows 打包 ([59158c6](https://github.com/MisterRabbit0w0/live-trans/commit/59158c6784915324f658eec4ba7a524cdd032a4d))
* clarify overview and prevent duplicate instances ([6ee1a96](https://github.com/MisterRabbit0w0/live-trans/commit/6ee1a960378e329aee0c8ffcc31bf4eba154ace7))
* clear font recovery after successful save ([76e9432](https://github.com/MisterRabbit0w0/live-trans/commit/76e9432ace41530748137e67ab0d2657819df0c5))
* harden qml packaging compatibility ([c895cfc](https://github.com/MisterRabbit0w0/live-trans/commit/c895cfc80c5d37c8a7f4d50720cc185812c1ea15))
* harden remaining runtime and settings paths ([fb973e2](https://github.com/MisterRabbit0w0/live-trans/commit/fb973e2fae7a33017f865be32ab896a8c154ad74))
* harden shutdown and release validation ([a005fbe](https://github.com/MisterRabbit0w0/live-trans/commit/a005fbeee8ae4de3d24632d7484433d5e8ef1040))
* **records:** 纪要异步任务、配置快照、内容绑定缓存与预算/截断保护 (FIX-003/004/005/017) ([a5649f3](https://github.com/MisterRabbit0w0/live-trans/commit/a5649f34c8cdaeacec61e242b72a22661e647e48))
* **release:** audit dependency lock sources and paths ([c23119d](https://github.com/MisterRabbit0w0/live-trans/commit/c23119d610b98cca5bfba2484c17ff5fdfc75450))
* **security:** 放行占位用户名路径，修复历史审计误报 ([84d0ba1](https://github.com/MisterRabbit0w0/live-trans/commit/84d0ba11a1c9c2f30ff16ba4457e12f4f1039ff4))
* serialize deferred runtime cleanup ([957763a](https://github.com/MisterRabbit0w0/live-trans/commit/957763af0e3f2b37aeb95040893add659afe964e))
* **session:** 正常停止排空尾句与在途工作，结果绑定采集时记录文件 (FIX-009) ([c592d1e](https://github.com/MisterRabbit0w0/live-trans/commit/c592d1e9fa33b3f774497c1e3e20b70c26a3576a))
* **style:** 格式化 packaging/icon.py 保证单行不超过 100 字符 ([a3177f4](https://github.com/MisterRabbit0w0/live-trans/commit/a3177f44ba77aca7d002c9ae0b92eb333670f9ac))
* **translate:** preserve Chinese script conversion ([7d3c571](https://github.com/MisterRabbit0w0/live-trans/commit/7d3c5711e9e24ba95cddf8b66ef903652972e370))
* **worker:** hello 握手前不再阻塞于 numpy 导入 (FIX-001 收尾) ([d420d3f](https://github.com/MisterRabbit0w0/live-trans/commit/d420d3f5ea08cdfcfb5d7f08bca8ac79408b8fdf))
* **worker:** hello 握手前去重依赖 + 启动路径探针诊断 ([39c8b6c](https://github.com/MisterRabbit0w0/live-trans/commit/39c8b6cfcb92eab6c471fcc14fe66750ac9ec185))


### Documentation

* 发行链与验收文档对齐 NSIS 现实，CHANGELOG 记录 0.2.0 (FIX-015, T2.9) ([07f3bb2](https://github.com/MisterRabbit0w0/live-trans/commit/07f3bb2743105da3fde877ef494cd2e1cb044c19))
* 更新 README 为 Tauri 架构、解耦流水线与 Mermaid 架构图 ([d8d62b6](https://github.com/MisterRabbit0w0/live-trans/commit/d8d62b60dcb9ecd0cbdd1f32b78876a30e1d5800))

## [0.2.0] - 2026-10-10

### 修复（v0.2 阻塞项）

- **纪要可靠性与响应**（FIX-003/004/005/017）：纪要生成移出核心事件循环，改为有界异步任务（单飞 + 完成事件 + 状态查询/取消）；提交时绑定当前配置快照；缓存按源内容哈希、模型、服务身份与提示词版本校验并原子写入，写失败上报；新增输入预算（`record.summary_max_chars`，默认 12 万字符）与截断/空输出判定，不再把不完整结果当作完整纪要。
- **记录与导出时间**（FIX-006）：记录页、复制文本、纪要与 Markdown 导出统一以会话起点换算会内时间，不再把 Unix 绝对时间误当分钟。
- **正常停止数据完整性**（FIX-009）：停止时先排空 VAD 尾段与在途识别/翻译（5 秒预算，超时降级为中止）；热切记录后迟到结果按采集时归属处理，不串入新文件。

### 发行与工程

- **桌面发行链**（T2.1/FIX-001/FIX-010）：发行物改为 Tauri NSIS 安装器 + 便携 ZIP，随包 `livetrans-core` onedir（冻结核心改 console 构建并保留管道通信）；移除 Inno Setup、独立单文件 EXE 与 PySide6 构建依赖。
- **发行路径安全**（FIX-002）：release 构建不再回退构建机路径与环境变量；缺失随包核心时给出明确错误。
- **端到端烟测**（T2.3）：构建链内置冻结核心管道烟测、worker hello 与壳二进制路径残留扫描（`smoke_frozen.py`）。
- **三端 CI**（T2.5/FIX-016）：CI 增加 Vitest、svelte-check、vite 生产构建与 cargo test/clippy；保留 Python、脱敏与打包检查。
- **版本单一来源**（T2.6）：`bump_version.py` 以 `pyproject.toml` 同步四处清单，CI 与标签校验强制一致。
- **CHANGELOG 自动化**（T2.7）：接入 release-please。
- **文档对齐**（T2.9/FIX-015）：发布、验收与 README 按现行发行链重写。

## [0.1.0] - 未发布

- 首个里程碑版本：迁移至 Tauri + Svelte 桌面壳与冻结 Python 核心的开发中状态，占位待首次发布。
