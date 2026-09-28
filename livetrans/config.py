"""配置定义与 JSON 持久化。

配置文件位于各平台的用户配置目录：Windows %APPDATA%/livetrans，
macOS ~/Library/Application Support/livetrans，Linux $XDG_CONFIG_HOME/livetrans。
"""
from __future__ import annotations

import dataclasses
import json
import os
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path


def config_dir() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA") or Path.home())
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    d = base / "livetrans"
    d.mkdir(parents=True, exist_ok=True)
    return d


def config_path() -> Path:
    return config_dir() / "config.json"


@dataclass
class AsrConfig:
    backend: str = "local"  # local | cloud
    # local
    model: str = "auto"  # auto | large-v3-turbo | medium | small | ...
    device: str = "auto"  # auto | cuda | cpu
    runtime: str = ""  # 本地模型进程使用的 Python 环境；空 = 与应用相同
    # cloud（OpenAI 兼容 /audio/transcriptions）
    cloud_base_url: str = "https://api.groq.com/openai/v1"
    cloud_api_key: str = ""
    cloud_model: str = "whisper-large-v3-turbo"
    # 通用
    language: str = "auto"  # auto | en | ja | ko | ...


@dataclass
class TranslateConfig:
    enabled: bool = True  # 是否开启翻译（关闭时仅进行语音识别与记录）
    # 本地 Ollama 与云端共用 OpenAI 兼容接口，仅 base_url/key/model 不同
    base_url: str = "http://localhost:11434/v1"
    api_key: str = "ollama"
    model: str = "qwen2.5:7b-instruct"
    target_language: str = "中文"

@dataclass
class SubtitleStyle:
    font_size: int = 22
    show_original: bool = True  # 双语
    max_lines: int = 3  # 同屏显示最近几条
    opacity: float = 0.75  # 背景不透明度
    width: int = 900


@dataclass
class UiConfig:
    silent_start: bool = False
    auto_translate: bool = False
    theme: str = "system"  # system | light | dark
    accent: str = "system"  # Material 3 种子色：system | #rrggbb
    reduce_motion: bool = False
    reduce_transparency: bool = False


@dataclass
class RecordConfig:
    enabled: bool = False  # 把原文、译文和时间保存到 records/，不含音频


@dataclass
class AppConfig:
    audio_source_mode: str = "system"  # system = 整个系统 | process = 指定软件
    audio_device: str = ""  # system 模式：平台设备标识，空 = 默认输出设备
    audio_process_name: str = ""  # process 模式：进程/应用名，如 chrome.exe、firefox
    asr: AsrConfig = field(default_factory=AsrConfig)
    translate: TranslateConfig = field(default_factory=TranslateConfig)
    subtitle: SubtitleStyle = field(default_factory=SubtitleStyle)
    ui: UiConfig = field(default_factory=UiConfig)
    record: RecordConfig = field(default_factory=RecordConfig)
    # VAD 参数
    vad_silence_ms: int = 500  # 停顿多久切句
    vad_max_segment_s: float = 8.0  # 最长强制切断
    vad_min_speech_ms: int = 250  # 短于此的语音丢弃
    vad_threshold: float = 0.35  # VAD 语音触发门限 (0.1 ~ 0.9，越小越灵敏)
    audio_gain_enabled: bool = True  # 自适应电平增益（保守型平滑增益）
    def save(self, path: Path | None = None) -> None:
        p = path or config_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        # Keep the previous configuration intact if writing or replacing fails.
        fd, temporary = tempfile.mkstemp(prefix=p.name + ".", suffix=".tmp", dir=p.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(dataclasses.asdict(self), stream, ensure_ascii=False, indent=2)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, p)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    @classmethod
    def load(cls, path: Path | None = None) -> AppConfig:
        p = path or config_path()
        if not p.exists():
            return cls()
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return cls()
        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: dict) -> AppConfig:
        cfg = cls()
        if not isinstance(data, dict):
            return cfg

        def assign(target, key, value):
            if not hasattr(target, key) or key.startswith("_"):
                return
            default = getattr(target, key)
            if type(value) is type(default) or (
                isinstance(default, float) and type(value) is int
            ):
                setattr(target, key, value)

        for section_name in ("asr", "translate", "subtitle", "ui", "record"):
            section_data = data.get(section_name)
            if isinstance(section_data, dict):
                section = getattr(cfg, section_name)
                for k, v in section_data.items():
                    if k in {f.name for f in dataclasses.fields(section)}:
                        assign(section, k, v)
        for k in (
            "vad_silence_ms", "vad_max_segment_s", "vad_min_speech_ms",
            "vad_threshold", "audio_gain_enabled",
            "audio_device", "audio_source_mode", "audio_process_name",
        ):
            if k in data:
                assign(cfg, k, data[k])
        legacy = data.get("audio_device_index")
        if "audio_device" not in data and type(legacy) is int and legacy >= 0:
            cfg.audio_device = str(legacy)
        return cfg
