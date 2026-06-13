# LiveTrans — 直播实时翻译

看外语直播（YouTube / Twitch / 任意客户端）时，把主播说的话实时翻译成中文，
以置顶悬浮窗显示**双语字幕**。

- **平台无关**：通过 WASAPI 环回捕获系统音频，任何能发声的应用都能翻译，无需虚拟声卡
- **可按软件捕获**：设置中切换"指定软件"模式后只捕获目标软件（如浏览器/直播客户端）的声音，不混入音乐、消息提示音等（需 Win10 2004+；目标软件需先发声才能出现在列表中，也可手动输入进程名）
- **默认全本地、零费用**：faster-whisper 识别 + Ollama 本地大模型翻译
- **可切云端**：识别和翻译都支持任意 OpenAI 兼容 API（Groq / DeepSeek / OpenAI 等），填 base_url + API key 即可

## 工作原理

```
系统音频 (WASAPI loopback) → Silero VAD 切句 → Whisper 识别 → LLM 翻译 → 悬浮字幕窗
```

原文先上屏（"…"占位译文），译文到达后补上，体感延迟约 2~4 秒。

## 安装

需要 Windows 10/11 + Python 3.10+。

```powershell
python -m venv .venv
.venv\Scripts\pip install -e ".[cuda]"     # 有 NVIDIA 显卡
# 或 .venv\Scripts\pip install -e .        # 无显卡（CPU/云端模式）
```

### 翻译后端（二选一）

**A. 本地 Ollama（默认，免费）**

1. 安装 [Ollama](https://ollama.com/download/windows)
2. 拉取翻译模型：`ollama pull qwen2.5:7b-instruct`（显存紧张可用 `qwen2.5:3b-instruct`）

**B. 云端 API**

托盘 → 设置 → 翻译，把 Base URL / API Key / 模型改成你的服务商，例如：

| 服务商 | Base URL | 模型示例 |
|---|---|---|
| DeepSeek | `https://api.deepseek.com/v1` | `deepseek-chat` |
| Groq（有免费层） | `https://api.groq.com/openai/v1` | `llama-3.3-70b-versatile` |
| OpenAI | `https://api.openai.com/v1` | `gpt-4o-mini` |

### 语音识别后端

默认本地 faster-whisper，启动时按空闲显存自动选档（首次运行会自动下载模型，需稍等）：

| 空闲显存 | 模型 |
|---|---|
| ≥ 10GB | large-v3-turbo (float16) |
| 5~10GB | large-v3-turbo (int8) |
| 3~5GB | small (int8) |
| 无 GPU | small (CPU int8) |

也可在设置中切到云端转写（如 Groq 的 `whisper-large-v3-turbo`，有免费层）。

## 使用

```powershell
.venv\Scripts\python -m livetrans.main
```

或直接双击根目录的 **`start.bat`**（无命令行窗口）。运行
`scripts\create_shortcut.ps1` 可在桌面生成快捷方式。

1. 播放任意外语直播/视频
2. 悬浮窗 2~4 秒内出现双语字幕（首次需等模型下载和加载）
3. 拖动窗口移动位置；**Ctrl+滚轮**调字号
4. 系统托盘图标：暂停/继续、隐藏字幕、设置（源语言、后端、样式）、退出

配置与日志位于 `%APPDATA%\livetrans\`。

## 分步排查

```powershell
.venv\Scripts\python scripts\test_capture.py    # 录5秒系统声音 → capture_test.wav
.venv\Scripts\python scripts\test_asr.py        # 转写上一步的 wav
.venv\Scripts\python scripts\test_translate.py  # 测试翻译端点
```

- 录不到声音：检查默认输出设备（声音设置），蓝牙耳机切换设备后需重启程序
- CUDA 报错 `cuBLAS_STATUS_NOT_SUPPORTED`：RTX 50xx (Blackwell) 等新架构显卡上已自动改用 `float16` 推理，若仍报错会回退 CPU，不影响使用
- 其他 CUDA 报错：会自动回退 CPU；要用 GPU 需确保安装了 `.[cuda]` 附加依赖且驱动较新
- 翻译一直"…"：检查 Ollama 是否在运行（`ollama list`），或设置里的云端配置

## 项目结构

```
livetrans/
├── main.py            # 入口：托盘 + 悬浮窗 + 管线装配
├── pipeline.py        # 线程编排：capture → vad → asr → translate → ui
├── config.py          # 配置 dataclass + JSON 持久化
├── audio/
│   ├── capture.py         # WASAPI 环回捕获（整个系统）
│   ├── process_capture.py # 按进程捕获（Process Loopback API）
│   └── vad.py             # Silero VAD 流式切句
├── asr/               # 语音识别：本地 faster-whisper / 云端
├── translate/         # 翻译：OpenAI 兼容（Ollama / 云端）
├── ui/                # 悬浮字幕窗、设置面板、系统托盘
└── assets/            # silero_vad.onnx
```

`scripts/` 下为分步排查工具（捕获 / VAD / 识别 / 翻译）。

## 许可

[MIT](LICENSE) © MisterRabbit0w0
