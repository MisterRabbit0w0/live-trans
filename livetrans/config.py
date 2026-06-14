"""配置定义与 JSON 持久化。

配置文件位于 %APPDATA%/livetrans/config.json。
"""
from __future__ import annotations

import dataclasses
import json
import os
from dataclasses import dataclass, field
from pathlib import Path


def config_dir() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home())
    d = Path(base) / "livetrans"
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
    # cloud（OpenAI 兼容 /audio/transcriptions）
    cloud_base_url: str = "https://api.groq.com/openai/v1"
    cloud_api_key: str = ""
    cloud_model: str = "whisper-large-v3-turbo"
    # 通用
    language: str = "auto"  # auto | en | ja | ko | ...


@dataclass
class TranslateConfig:
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
class AppConfig:
    audio_source_mode: str = "system"  # system = 整个系统 | process = 指定软件
    audio_device_index: int = -1  # system 模式：-1 = 默认输出设备的环回
    audio_process_name: str = ""  # process 模式：进程名，如 chrome.exe
    asr: AsrConfig = field(default_factory=AsrConfig)
    translate: TranslateConfig = field(default_factory=TranslateConfig)
    subtitle: SubtitleStyle = field(default_factory=SubtitleStyle)
    # VAD 参数
    vad_silence_ms: int = 500  # 停顿多久切句
    vad_max_segment_s: float = 8.0  # 最长强制切断
    vad_min_speech_ms: int = 250  # 短于此的语音丢弃

    def save(self, path: Path | None = None) -> None:
        p = path or config_path()
        p.write_text(
            json.dumps(dataclasses.asdict(self), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    @classmethod
    def load(cls, path: Path | None = None) -> AppConfig:
        p = path or config_path()
        if not p.exists():
            return cls()
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return cls()
        cfg = cls()
        for section_name in ("asr", "translate", "subtitle"):
            section_data = data.get(section_name)
            if isinstance(section_data, dict):
                section = getattr(cfg, section_name)
                for k, v in section_data.items():
                    if hasattr(section, k):
                        setattr(section, k, v)
        for k in (
            "vad_silence_ms", "vad_max_segment_s", "vad_min_speech_ms",
            "audio_device_index", "audio_source_mode", "audio_process_name",
        ):
            if k in data:
                setattr(cfg, k, data[k])
        return cfg
