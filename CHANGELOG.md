# Changelog

本文件遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循[语义化版本](https://semver.org/lang/zh-CN/)。条目由
release-please 根据 Conventional Commits 自动汇总，勿手工编辑已发布段落。

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
