<div align="center">

# LiveTrans

[中文](README.md) | **English**

Real-time bilingual floating subtitles for foreign-language livestreams, raw videos, online classes and meetings, with AI meeting notes.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Release](https://img.shields.io/github/v/release/MisterRabbit0w0/live-trans?include_prereleases)](https://github.com/MisterRabbit0w0/live-trans/releases)
[![Platform](https://img.shields.io/badge/platform-Windows%20x64-0078d4.svg)](#install)
[![Tauri v2](https://img.shields.io/badge/Tauri-v2-orange.svg)](https://tauri.app/)
[![Svelte 5](https://img.shields.io/badge/Svelte-5-ff3e00.svg)](https://svelte.dev/)

<!-- Screenshot slot: docs/assets/overlay.png — see docs/assets/README.md -->

</div>

LiveTrans captures system audio, segments speech with streaming VAD, transcribes it locally with faster-whisper, translates it, and shows bilingual subtitles in an always-on-top overlay. With recording on, browse a timestamped transcript afterwards and generate meeting notes in one click.

> The UI is currently Chinese only. Labels below are given as「中文」(English).

---

## Features

- **System-wide audio capture**: works with any app — livestream clients, meeting software, video players. On Windows, capture the whole system or a single app.
- **Four run modes**, hot-swappable while running without restarting the speech engine (see [Choosing a mode](#choosing-a-mode)).
- **AI meeting notes**: topic and core message, per-topic highlights, key decisions and action items. Full or brief (<200 characters) versions, exportable as Markdown.
- **Local speech recognition**: faster-whisper runs in an isolated worker process — a crash never takes down the UI, and VRAM is released on exit. The model size is picked automatically from free VRAM.
- **Bring your own translator**: local Ollama (offline, free) or any OpenAI-compatible cloud API.
- **Lightweight shell**: Tauri v2 + Svelte 5, lives in the system tray.

<!-- Screenshot slots: docs/assets/main-window.png, docs/assets/records.png -->

## Install

Download from [Releases](https://github.com/MisterRabbit0w0/live-trans/releases):

| File | Description |
|---|---|
| `LiveTrans-x.y.z-windows-x64-setup.exe` | Installer (NSIS) with Start menu entry and uninstaller |
| `LiveTrans-x.y.z-windows-x64-portable.zip` | Portable, unzip and run |
| `SHA256SUMS.txt` | Checksums to verify your download |

- Installer and portable builds share settings in `%APPDATA%\livetrans`.
- Release builds are CPU only. For NVIDIA GPU acceleration, [run from source](#development) with `.[cuda]`.
- Binaries are unsigned; Windows SmartScreen may warn on first launch — choose "More info → Run anyway".
- The single-file `standalone.exe` from 0.1.0 is no longer shipped since 0.2.0.

> **Platforms**: Windows 10/11 x64 is the only official release target. macOS (ScreenCaptureKit) and Linux (PulseAudio / PipeWire) capture backends exist in source but are experimental and not release-tested.

## Quick start

1. **Download a speech model** (local recognition only): open「语音识别」(Speech recognition) and click download in the model panel (a few hundred MB and up; needs access to Hugging Face). Models are not bundled. Skip this if you only use cloud transcription.
2. **Set up translation**: in「翻译」(Translation), fill in Base URL, API key and model, and pick a target language (see [Translation](#translation)).
3. **Pick an audio source** in「声音来源」(Audio source): whole system or a specific app.
4. **Turn on recording if you want notes**: enable「保存翻译记录」(Save transcripts) in「通用」(General). It is off by default; without it nothing is saved and Records & notes stays empty.
5. **Go**: click「应用设置」(Apply, `Ctrl + Enter`), start from「概览」(Overview), and the overlay appears.
6. **Afterwards**: open「记录与纪要」(Records & notes) to generate and export notes. Sessions recorded with translation on are bilingual; mode 3 records contain the original text only.

<!-- Demo GIF slot: docs/assets/quickstart.gif -->

## Choosing a mode

| Use case | Mode | What it does |
|---|---|---|
| International meetings, keep a record | 1 · Translate + record | Live bilingual subtitles, saved line by line |
| Livestreams / raw videos | 2 · Translate only | Subtitles only, no session transcript saved |
| Meeting minutes without spending tokens | 3 · Record only | No translation API calls while transcribing; large original-language subtitles |
| Plain dictation | 4 · Original subtitles | Original-language captions only, no translation or recording |

## Recognition and translation

### Speech recognition

- **Local faster-whisper (default)**. The「自动」(Auto) setting picks by free VRAM:
  - ≥ 5000 MB: `large-v3-turbo` (CUDA float16)
  - 2000–4999 MB: `small` (CUDA float16)
  - no usable GPU: `small` (CPU int8)
- **Cloud transcription**: any OpenAI-compatible `/audio/transcriptions` endpoint. **Audio is sent to that service.**

### Translation

Both local and cloud use the OpenAI-compatible API — only Base URL / key / model differ.

- **Local Ollama (default, free, offline)**: install [Ollama](https://ollama.com/), run `ollama pull qwen2.5:7b-instruct` (or `qwen2.5:3b-instruct` on smaller GPUs). The defaults work as-is: Base URL `http://localhost:11434/v1`, key `ollama`.
- **Cloud**:

| Provider | Base URL | Example model |
|---|---|---|
| DeepSeek | `https://api.deepseek.com/v1` | `deepseek-chat` |
| Groq (free tier) | `https://api.groq.com/openai/v1` | `llama-3.3-70b-versatile` |
| OpenAI | `https://api.openai.com/v1` | `gpt-4o-mini` |

19 built-in target languages. AI meeting notes reuse the same endpoint.

<!-- TODO(after #22): document translation context memory and retry -->

## Overlay and shortcuts

- **Move**: drag any non-text area of the overlay.
- **Font size**: `Ctrl + mouse wheel` over the subtitles. More options in「字幕外观」(Subtitle appearance): show original, lines on screen, background opacity, width.
- **Always on top**. Click-through is **not** supported yet.
- **Control center**: `Ctrl + Enter` applies settings, `Ctrl + Q` quits and releases the model process.
- **Tray**: closing the control center hides it to the tray; left-click the icon to reopen. The tray menu starts/stops translation, toggles subtitles, or quits.

## Troubleshooting

| Symptom | Check |
|---|---|
| No subtitles | Correct audio source? Volume too low (below -60 dBFS the auto gain stops amplifying — raise the source volume, or lower「触发灵敏度 (VAD 阈值)」(VAD threshold) in Speech recognition)? Local model downloaded? |
| Per-app capture misses audio | Process Loopback works best on Windows 11 / Build 20348+ |
| High latency | Use a smaller model or a faster translation endpoint |
| Bad translations | Check the target language; try a stronger model |
| Anything else | 「通用」(General) →「打开日志目录」(Open log folder), attach logs to an [issue](https://github.com/MisterRabbit0w0/live-trans/issues) — check them for secrets first |

## Privacy

- Audio capture, VAD and local recognition never leave your machine.
- What goes out depends only on your settings:
  - **Translation / notes**: recognized text goes to your configured endpoint (local Ollama by default).
  - **Cloud transcription**: if selected, audio goes to that service.
  - **Model download**: contacts Hugging Face.
- With local recognition + local Ollama, everyday use needs no internet.
- API keys are stored in plain text in your local config (`%APPDATA%\livetrans`) and only passed between local processes; they are never uploaded anywhere except the endpoint you configured. No telemetry.

## Development

Requires Python 3.10+, Rust 1.85+, Node.js 22.12+ (24 recommended, same as CI).

```powershell
git clone https://github.com/MisterRabbit0w0/live-trans.git
cd live-trans
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[cuda]"   # or: pip install -e .  (CPU / cloud only)

cd desktop
npm ci
npm run tauri:dev          # or double-click start.bat in the repo root
```

- Architecture and layout: [docs/architecture.md](docs/architecture.md) (Chinese)
- Building release packages and the release process: [docs/releasing.md](docs/releasing.md) (Chinese)
- Contributing: [CONTRIBUTING.md](CONTRIBUTING.md)

```powershell
pip install ruff==0.15.17   # same version as CI
python -m unittest discover -s tests -v
npm test --prefix desktop
npm run check --prefix desktop
cargo test --locked --manifest-path desktop/src-tauri/Cargo.toml
ruff check .
```

## License

[MIT](LICENSE). Third-party components are under their own licenses — see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
