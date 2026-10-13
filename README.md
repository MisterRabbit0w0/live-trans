<div align="center">

# LiveTrans

**中文** | [English](README_EN.md)

外语直播、生肉视频、网课和线上会议的实时双语悬浮字幕，附带 AI 会议纪要。

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Release](https://img.shields.io/github/v/release/MisterRabbit0w0/live-trans?include_prereleases)](https://github.com/MisterRabbit0w0/live-trans/releases)
[![Platform](https://img.shields.io/badge/platform-Windows%20x64-0078d4.svg)](#安装)
[![Tauri v2](https://img.shields.io/badge/Tauri-v2-orange.svg)](https://tauri.app/)
[![Svelte 5](https://img.shields.io/badge/Svelte-5-ff3e00.svg)](https://svelte.dev/)

<!-- 截图位：docs/assets/overlay.png（字幕浮层叠在视频上的效果），见 docs/assets/README.md -->

</div>

LiveTrans 捕获系统音频，用流式 VAD 分句，经本地 faster-whisper 识别后翻译，把双语字幕置顶浮在任意画面上。会后可以在「记录与纪要」里按时间戳浏览双语对照，一键生成会议纪要。

---

## 核心特性

- **系统级音频捕获**：不限来源，直播客户端、会议软件、播放器的声音都能获取。Windows 支持整机环回，也可以只捕获指定软件的声音。
- **四种运行模式**，运行中可一键热切（见 [模式选择](#模式选择)）。
- **AI 会议纪要**：提炼主题主旨、各议题要点、关键结论和 Action Items；支持「完整会议纪要」和「极简速览（<200 字）」，可导出 Markdown。
- **本地识别**：faster-whisper 在独立子进程中运行，崩溃不影响主窗口，退出后释放显存；按空闲显存自动选模型档位。
- **翻译接口自选**：本地 Ollama（全离线、免费），或任意 OpenAI 兼容的云端服务。
- **轻量桌面壳**：Tauri v2 + Svelte 5，常驻系统托盘。

<!-- 截图位：docs/assets/main-window.png（控制中心概览页）、docs/assets/records.png（记录与纪要工作台） -->

## 安装

从 [Releases](https://github.com/MisterRabbit0w0/live-trans/releases) 下载对应版本：

| 文件 | 说明 |
|---|---|
| `LiveTrans-x.y.z-windows-x64-setup.exe` | 安装版（NSIS），带开始菜单项和卸载程序 |
| `LiveTrans-x.y.z-windows-x64-portable.zip` | 便携版，解压即用 |
| `SHA256SUMS.txt` | 校验和，用于核对下载是否完整 |

- 安装版和便携版共用 `%APPDATA%\livetrans` 里的配置。
- 发行包只带 CPU 推理。要用 NVIDIA GPU 加速，请[从源码运行](#开发)并安装 `.[cuda]`。
- 程序未做代码签名，首次运行时 Windows SmartScreen 可能拦截，选「更多信息 → 仍要运行」即可。

> **平台支持**：正式发行只有 Windows 10/11 x64。macOS（ScreenCaptureKit）和 Linux（PulseAudio / PipeWire）的音频后端有源码实现，属于实验性支持。

## 快速上手

1. **下载识别模型**（用本地识别时）：打开「语音识别」页，在模型面板点击下载（几百 MB 起，需要能访问 Hugging Face）。模型不随安装包分发。只用云端转写可以跳过这一步。
2. **配置翻译**：在「翻译」页填写 Base URL、API Key 和模型名，选好目标语言（见 [翻译接口](#翻译接口)）。
3. **选声音来源**：在「声音来源」页选择整机环回，或指定某个软件。
4. **要出纪要的话先开记录**：在「通用」页打开「保存翻译记录」（默认关闭）。不开的话不会存会话，「记录与纪要」里是空的。
5. **开始**：点「应用设置」（`Ctrl + Enter`），回到「概览」启动，字幕浮层就会出现。
6. **会后整理**：到「记录与纪要」生成纪要并导出。

<!-- 演示 GIF 位：docs/assets/quickstart.gif（从启动到字幕出现的全过程，建议 ≤ 15 秒） -->

## 模式选择

| 场景 | 推荐模式 | 说明 |
|---|---|---|
| 跨国会议，边听边留档 | 边翻译边记录 | 实时双语字幕，同时逐句存盘 |
| 外语直播 / 生肉视频 | 仅实时翻译 | 只显示字幕，不保存会话记录 |
| 会议速记，不想花 Token | 仅语音记录 | 识别期间不调用翻译接口，字幕显示大字号原文 |
| 只看原文听写 | 纯原文字幕 | 只显示原文字幕，不翻译也不记录 |

## 识别与翻译设置

### 语音识别

- **本地 faster-whisper（默认）**：「自动」档按空闲显存选择：
  - 显存 ≥ 5000 MB：`large-v3-turbo`（CUDA float16）
  - 显存 2000–4999 MB：`small`（CUDA float16）
  - 没有可用 GPU：`small`（CPU int8）
- **云端转写**：任意兼容 OpenAI `/audio/transcriptions` 的服务。选这个时**音频会发到该服务**。

### 翻译/纪要接口

翻译和纪要共用端口，本地 Ollama 和云端服务都走 OpenAI 兼容接口：

- **本地 Ollama（默认，免费、离线）**：安装 [Ollama](https://ollama.com/) 后下载模型，推荐 `qwen3.5` 系列模型
- **云端**：

| 服务商 | Base URL | 模型示例 |
|---|---|---|
| DeepSeek | `https://api.deepseek.com/v1` | `deepseek-chat` |
| Groq（有免费额度） | `https://api.groq.com/openai/v1` | `llama-3.3-70b-versatile` |
| OpenAI | `https://api.openai.com/v1` | `gpt-4o-mini` |

内置 19 种目标语言（中文简繁、英、日、韩、法、德、西、葡、俄等）。

<!-- TODO(#22 合入后)：补充「翻译上下文记忆与失败重试」说明 -->
## 字幕浮层与快捷操作

- **拖动**：按住浮层上文字以外的区域拖到任意位置。
- **字号**：鼠标停在字幕上按 `Ctrl + 滚轮` 调节；「字幕外观」页还能设置是否显示原文、同屏条数、背景不透明度和浮层宽度。
- **置顶**：浮层始终在最上层。目前**不支持**点击穿透。
- **控制中心**：`Ctrl + Enter` 应用设置，`Ctrl + Q` 退出并释放模型进程。
- **托盘**：关闭控制中心只是隐藏到托盘；单击托盘图标重新打开，右键菜单可以开始/停止翻译、切换字幕显示或退出。

## 记录与 AI 纪要

模式 1 / 3 下（「通用」页的「保存翻译记录」开着时）会话会存到本地，「记录与纪要」工作台按会内时间戳列出。开着翻译录的会话是双语对照，模式 3 只有原文。支持：

- 一键复制，或导出为 Markdown；
- 生成「完整会议纪要」或「极简速览（<200 字）」，内容包括主题与核心主旨、各议题要点、关键结论和 Action Items；
- 纪要用的是「翻译」页配置的接口，选云端服务时记录文本会发给该服务。

## 故障排查

| 现象 | 先检查 |
|---|---|
| 没有字幕 | 声音来源选对没有（整机环回还是指定软件）；音量是否过小（低于 -60 dBFS 时自动增益不再放大，可以调高源音量，或在「语音识别」页调低「触发灵敏度 (VAD 阈值)」）；本地识别的模型下载好没有 |
| 只能捕获部分软件 | 指定软件捕获（Process Loopback）建议在 Windows 11 / Build 20348+ 上用 |
| 延迟高 | 换小一档的模型；换响应更快的翻译接口 |
| 译文不对 | 检查目标语言；换更强的翻译模型 |
| 其他异常 | 在「通用」页点「打开日志目录」，把日志附在 [Issue](https://github.com/MisterRabbit0w0/live-trans/issues) 里（提交前请检查有没有密钥） |

## 隐私

- 音频捕获、VAD 分句和本地识别都在本机完成。
- 会发到外部的数据只取决于你的配置：
  - **翻译 / 纪要**：识别出的文本发给「翻译」页的接口。默认是本地 Ollama，不出本机。
  - **云端识别**：选了它，音频会发给对应服务。
  - **下载模型**：会访问 Hugging Face。
- 本地识别 + 本地 Ollama 时，日常使用不需要联网。
- API Key 以明文保存在本机配置（`%APPDATA%\livetrans`）里，只在本机进程之间传递，不会上传到配置接口以外的地方。

## 常见问题

**和浏览器字幕插件有什么区别？**
LiveTrans 捕获的是系统级音频，所以不限浏览器，桌面客户端、会议软件和播放器都能用。

**能用 GPU 吗？**
发行包只有 CPU 推理。有 NVIDIA 显卡的话从源码安装 `.[cuda]`，「自动」档会按显存选更大的模型。

**会收集使用数据吗？**
不会，应用没有遥测。

## 开发

需要 Python 3.10+、Rust 1.85+、Node.js 22.12+（推荐 24，与 CI 一致）。

```powershell
git clone https://github.com/MisterRabbit0w0/live-trans.git
cd live-trans
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[cuda]"   # 只用 CPU 或纯云端时改成 pip install -e .

cd desktop
npm ci
npm run tauri:dev          # 也可以在仓库根目录双击 start.bat
```

- 架构与目录结构：[docs/architecture.md](docs/architecture.md)
- 构建发行包（NSIS + 便携 ZIP）和发布流程：[docs/releasing.md](docs/releasing.md)。单独 `cargo build --release` 出来的壳没有随包核心，不能当发行产物用。
- 界面验收清单：[docs/frontend-validation.md](docs/frontend-validation.md)
- 贡献指南：[CONTRIBUTING.md](CONTRIBUTING.md)

### 测试与质量保证

```powershell
pip install ruff==0.15.17                         # 与 CI 同版本
python -m unittest discover -s tests -v           # Python 离线回归
npm test --prefix desktop                         # Vitest
npm run check --prefix desktop                    # svelte-check
cargo test --locked --manifest-path desktop/src-tauri/Cargo.toml
ruff check .
```

## 开源许可

[MIT License](LICENSE)。第三方组件遵循各自的许可证，详见 [第三方声明](THIRD_PARTY_NOTICES.md)。
