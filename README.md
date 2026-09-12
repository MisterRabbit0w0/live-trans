# LiveTrans

看外语直播（YouTube / Twitch / 任意客户端）时，把主播说的话实时翻译成中文，
以置顶悬浮窗显示**双语字幕**。

- **系统音频捕获**：通过 Windows WASAPI 环回获取播放声音，无需虚拟声卡
- **可按软件捕获**：只捕获指定进程及其子进程。需要 Windows Build 20348+，建议 Windows 11；软件发声后可从列表选择，也可手动输入进程名
- **本地识别与翻译**：faster-whisper 识别 + Ollama 翻译，需要下载模型并安装 Ollama
- **可切云端**：识别和翻译都支持任意 OpenAI 兼容 API（Groq / DeepSeek / OpenAI 等），填 base_url + API key 即可
- **统一控制中心**：QML 分类设置、跨页草稿、字幕预览和统一应用；概览与托盘共享运行状态
- **Liquid Glass 外观**：浅色 / 深色 / 跟随系统，Windows 原生 Desktop Acrylic 与实色回退，支持减少动态和透明效果

## 工作原理

```
系统音频 (WASAPI loopback) → Silero VAD 切句 → Whisper 识别 → LLM 翻译 → 悬浮字幕窗
```

原文先上屏，译文到达后补全。延迟取决于切句设置、模型、硬件和服务响应速度。

## 安装

当前支持 Windows x64。系统音频捕获可用于 Windows 10/11，指定软件捕获的版本要求见 [微软示例](https://learn.microsoft.com/en-us/samples/microsoft/windows-classic-samples/applicationloopbackaudio-sample/)。

### 安装程序与独立 EXE

发布版本可从 [GitHub Releases](https://github.com/MisterRabbit0w0/live-trans/releases) 下载。打包工作流生成以下三种 Windows 产物，均内置 Python：

| 文件 | 使用方式 |
|---|---|
| `LiveTrans-版本-windows-x64-setup.exe` | 按当前用户安装，创建开始菜单入口，可选桌面快捷方式 |
| `LiveTrans-版本-windows-x64-portable.zip` | 完整解压后运行 `LiveTrans.exe`，保留旁边的 `_internal` 文件夹 |
| `LiveTrans-版本-windows-x64-standalone.exe` | 直接运行，启动时会先解压内置依赖，体积与启动耗时较大 |

发行包默认用 CPU 进行本地识别，也可切换云端识别。包内不包含 CUDA DLL、Whisper 模型、Ollama 或翻译模型。首次使用本地识别时会下载 Whisper 模型；需要 GPU 时使用下面的源码安装方式。

产物附带 `SHA256SUMS.txt`、依赖版本清单和第三方许可证。当前工作流没有配置代码签名；Windows 可能显示未知发布者提示。卸载安装版会保留 `%APPDATA%\livetrans` 下的配置与日志，以及下载的模型缓存。

### 从源码安装

需要 Python 3.10+、PySide6 6.8+。用于构建发行包的依赖单独锁定在 `packaging/requirements-windows.lock`。

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

控制中心 → 翻译，编辑服务地址 / 密钥 / 模型，点击底部「应用设置」，例如：

| 服务商 | Base URL | 模型示例 |
|---|---|---|
| DeepSeek | `https://api.deepseek.com/v1` | `deepseek-chat` |
| Groq（有免费层） | `https://api.groq.com/openai/v1` | `llama-3.3-70b-versatile` |
| OpenAI | `https://api.openai.com/v1` | `gpt-4o-mini` |

### 语音识别后端

默认本地 faster-whisper，开始翻译时按空闲显存自动选档（首次使用会自动下载模型，需稍等）：

| 空闲显存 | 模型 |
|---|---|
| ≥ 5000MB | large-v3-turbo (CUDA float16) |
| 2000~4999MB | small (CUDA float16) |
| 无 GPU | small (CPU int8) |

该自动选档用于源码运行；CPU 发行包自动选择 `small` 和 CPU int8。也可在设置中切到云端转写。

## 使用

```powershell
.venv\Scripts\python -m livetrans.main
```

或直接双击根目录的 **`start.bat`**（无命令行窗口）。运行
`scripts\create_shortcut.ps1` 可在桌面生成快捷方式。

1. 启动后进入「概览」，首次使用先在分类页面确认声音来源、识别和翻译配置，再点击「应用设置」。
2. 播放直播 / 视频，点击「开始翻译」。模型准备完成后显示悬浮字幕，原文先出现，译文随后补全。
3. 在概览或托盘暂停 / 继续 / 停止，或切换字幕显示。拖动字幕移动位置；**Ctrl+滚轮**调整字号，设置页会同步更新。
4. 关闭控制中心会隐藏到托盘，设置草稿保留。双击托盘图标或选择「打开控制中心」可回到同一个窗口；退出时若有未应用修改，会询问丢弃或返回设置。

### 分类设置与应用

| 页面 | 内容 |
|---|---|
| 概览 | 运行状态、声音来源、模型、启停控制、最近字幕 |
| 声音来源 | 系统 / 指定软件、输出设备、进程刷新与手动输入 |
| 语音识别 | 本地 / 云端、源语言、模型；高级选项包含计算设备与切句参数 |
| 翻译 | 服务地址、密钥、模型、目标语言 |
| 字幕外观 | 字号、双语、条数、背景不透明度、宽度与面板内预览 |
| 通用 | 启动行为、主题、减少动态 / 透明效果、打开日志目录 |

设置草稿在页面之间保留。预览只影响设置面板，点击「应用设置」才会保存并生效；「还原修改」恢复到已保存的配置。无效字段会标记，保存失败会保留草稿。

字幕与界面外观修改直接生效，不重启或清空字幕。当前启用的声音、识别、翻译或切句配置变化会结束旧会话，再启动一次新会话，并保留暂停状态。重启失败会显示「设置已保存，启动失败」，可修改后重试。

快捷键：**Ctrl+Enter** 应用设置，**Ctrl+,** 打开通用，**Ctrl+Q** 退出。主窗口支持拖动、双击标题区域最大化 / 还原和边缘缩放；**Alt+空格** 或标题区域右键可打开窗口系统菜单。

### 启动行为

「静默启动」和「启动后自动翻译」默认都关闭，两个选项互相独立：

| 静默启动 | 自动翻译 | 启动结果 |
|---|---|---|
| 关闭 | 关闭 | 显示概览，等待手动开始 |
| 开启 | 关闭 | 仅在托盘待命 |
| 关闭 | 开启 | 显示控制中心并开始翻译，字幕正常显示 |
| 开启 | 开启 | 隐藏控制中心并开始翻译，字幕正常显示；失败时托盘通知 |

### 窗口材质与辅助显示

窗口通过公开的 `DWMWA_SYSTEMBACKDROP_TYPE` 请求 Desktop Acrylic，不截取桌面来模拟模糊。
该接口需要 Windows Build 22621+；旧系统、接口失败、减少透明效果或高对比模式下使用实色。
Windows 也可能自行将材质替换为实色；API 成功不等于当前桌面一定显示模糊。
控制中心失去焦点时遵循 Windows 的材质回退。字幕浮层单独保留活动材质外观，不抢走播放器的输入焦点。
详见 [微软系统背景材质文档](https://learn.microsoft.com/en-us/windows/win32/api/dwmapi/ne-dwmapi-dwm_systembackdrop_type)。

默认跟随系统主题，并尊重系统的动画、透明度和高对比偏好。字幕保持深色底和高对比文字；实色回退时背景不透明度不参与合成。

配置与日志位于 `%APPDATA%\livetrans\`。

翻译目标语言通过下拉框选择；旧配置中的自定义语言会保留在列表中。
标题栏、任务栏与托盘共用 [无文字 SVG 图标](livetrans/assets/livetrans.svg)。

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
├── main.py            # QML 窗口、控制器、材质与托盘装配
├── pipeline.py        # 独立管线，结构化事件汇报，不依赖窗口
├── config.py          # 兼容旧字段的 JSON 配置与原子保存
├── audio/
│   ├── capture.py         # WASAPI 环回捕获（整个系统）
│   ├── process_capture.py # 按进程捕获（Process Loopback API）
│   └── vad.py             # Silero VAD 流式切句
├── asr/               # 语音识别：本地 faster-whisper / 云端
├── translate/         # 翻译：OpenAI 兼容（Ollama / 云端）
├── ui/
│   ├── controller.py      # 共用状态与应用操作
│   ├── runtime.py         # 后台串行生命周期、会话隔离
│   ├── settings.py        # 草稿、校验、变更分类
│   ├── subtitle_model.py  # 增量字幕模型
│   ├── materials.py       # 原生材质与系统辅助显示偏好
│   ├── window_controls.py # Windows 客户区、原生缩放、系统菜单与透明底层
│   ├── tray.py            # 系统托盘
│   └── qml/               # 两个窗口、页面、统一控件和矢量图标
└── assets/            # VAD 模型与应用 SVG 图标
```

`scripts/` 下为分步排查工具（捕获 / VAD / 识别 / 翻译）。

## 开发与验收

```powershell
.venv\Scripts\pip install ruff build
.venv\Scripts\python -m unittest discover -s tests -v
.venv\Scripts\ruff check .
.venv\Scripts\python -m compileall -q livetrans scripts tests
.venv\Scripts\python -m build
.venv\Scripts\python scripts\check_package.py
```

自动测试使用假捕获和假引擎，不录音、不下载模型、不请求真实 API，覆盖管线启停 / 失败 / 会话隔离、配置应用、四种启动组合及 QML 交互。QML、应用 SVG 图标和 VAD 资源均检查 wheel / sdist 收录情况。

独立交互预览使用临时配置和模拟字幕，不修改用户配置：

```powershell
.venv\Scripts\python scripts\preview_ui.py
# 截取所有页面，分别将 scale 设为 1 / 1.5 / 2 检查 DPI
.venv\Scripts\python scripts\preview_ui.py --capture .cache/ui --theme dark --scale 1.5 --opaque
# 实际桌面合成检查：保持预览不被遮挡，在彩色测试背景上观察真实材质
.venv\Scripts\python scripts\preview_ui.py --backdrop --desktop --capture .cache/material
```

无桌面的 CI 使用 `QT_QPA_PLATFORM=offscreen` 和 `QT_QUICK_BACKEND=software`。原生毛玻璃、系统窗口操作、实际中文输入法及真实音频 / API 仍需在 Windows 桌面上检查。最近一次验证范围见 [界面验收记录](docs/frontend-validation.md)。

## 构建与发布

- `CI`：检查代码、敏感文件与完整 Git 历史，运行 Windows 离线回归，构建 Python wheel / sdist 并检查资源。
- `Windows packages`：可从 Actions 手动运行，构建便携 ZIP、单文件 EXE、安装程序和 SHA-256 清单，不发布 Release。
- `Release`：推送匹配项目版本的 `vX.Y.Z` 标签后，先通过 CI，再构建 Windows 产物，最后创建 GitHub Release 草稿。维护者完成实机验收后发布草稿。

完整命令、依赖更新和发行包限制见 [发布指南](docs/releasing.md)。贡献方式见 [CONTRIBUTING.md](CONTRIBUTING.md)，敏感信息处理见 [SECURITY.md](SECURITY.md)。

## 许可

[MIT](LICENSE) © MisterRabbit0w0。发行包中的依赖使用各自的许可证，见 [第三方声明](THIRD_PARTY_NOTICES.md)。
