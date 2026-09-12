"""A single settings draft shared by every QML page."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict
from urllib.parse import urlsplit

from PySide6.QtCore import Property, QObject, Signal, Slot

from ..config import AppConfig

TARGET_LANGUAGES = (
    ("中文（简体）", "中文"), ("中文（繁体）", "繁体中文"),
    ("英语", "英语"), ("日语", "日语"), ("韩语", "韩语"),
    ("法语", "法语"), ("德语", "德语"), ("西班牙语", "西班牙语"),
    ("葡萄牙语", "葡萄牙语"), ("俄语", "俄语"), ("意大利语", "意大利语"),
    ("阿拉伯语", "阿拉伯语"), ("印地语", "印地语"), ("泰语", "泰语"),
    ("越南语", "越南语"), ("印度尼西亚语", "印度尼西亚语"),
    ("土耳其语", "土耳其语"), ("荷兰语", "荷兰语"), ("波兰语", "波兰语"),
)


def validate_config(cfg: AppConfig) -> dict[str, str]:
    errors = {}

    def required(key, value, message="请填写此项"):
        if not value.strip():
            errors[key] = message

    def endpoint(key, value):
        try:
            url = urlsplit(value)
            valid = url.scheme in ("http", "https") and bool(url.hostname) and bool(url.port or 1)
            valid = valid and not url.username and not url.password
        except ValueError:
            valid = False
        if not valid:
            errors[key] = "请输入有效的 HTTP 或 HTTPS 服务地址（凭据请填入密钥栏）"

    if cfg.audio_source_mode not in ("system", "process"):
        errors["audio_source_mode"] = "请选择声音来源"
    if cfg.audio_source_mode == "process":
        required("audio_process_name", cfg.audio_process_name, "请选择或输入目标进程名")
    if cfg.asr.backend == "cloud":
        endpoint("asr.cloud_base_url", cfg.asr.cloud_base_url)
        required("asr.cloud_model", cfg.asr.cloud_model)
    elif cfg.asr.backend == "local":
        required("asr.model", cfg.asr.model)
        if cfg.asr.device not in ("auto", "cuda", "cpu"):
            errors["asr.device"] = "请选择计算设备"
    else:
        errors["asr.backend"] = "请选择识别方式"
    endpoint("translate.base_url", cfg.translate.base_url)
    required("translate.model", cfg.translate.model)
    required("translate.target_language", cfg.translate.target_language)
    for key, value, low, high in (
        ("vad_silence_ms", cfg.vad_silence_ms, 250, 1000),
        ("vad_max_segment_s", cfg.vad_max_segment_s, 1, 30),
        ("vad_min_speech_ms", cfg.vad_min_speech_ms, 50, 1000),
        ("subtitle.font_size", cfg.subtitle.font_size, 10, 48),
        ("subtitle.max_lines", cfg.subtitle.max_lines, 1, 10),
        ("subtitle.opacity", cfg.subtitle.opacity, 0, 1),
        ("subtitle.width", cfg.subtitle.width, 300, 2400),
    ):
        if not low <= value <= high:
            errors[key] = f"请输入 {low}–{high} 之间的数值"
    if cfg.vad_min_speech_ms > cfg.vad_max_segment_s * 1000:
        errors["vad_min_speech_ms"] = "最短语音不能长于最长句子"
    if cfg.ui.theme not in ("system", "light", "dark"):
        errors["ui.theme"] = "请选择外观主题"
    return errors


def engine_config(cfg: AppConfig) -> dict:
    """Only changes to the active engine inputs require a restart."""
    data = asdict(cfg)
    data.pop("subtitle")
    data.pop("ui")
    if cfg.audio_source_mode == "system":
        data.pop("audio_process_name")
    else:
        data.pop("audio_device_index")
    if cfg.asr.backend == "local":
        for key in ("cloud_base_url", "cloud_api_key", "cloud_model"):
            data["asr"].pop(key)
    else:
        for key in ("model", "device"):
            data["asr"].pop(key)
    return data


class SettingsStore(QObject):
    changed = Signal()

    def __init__(self, cfg: AppConfig, parent=None):
        super().__init__(parent)
        self._saved = asdict(cfg)
        self._draft = deepcopy(self._saved)
        self._errors: dict[str, str] = {}

    @Property("QVariantMap", notify=changed)
    def draft(self):
        return deepcopy(self._draft)

    @Property("QVariantMap", notify=changed)
    def errors(self):
        return self._errors

    @Property(bool, notify=changed)
    def dirty(self):
        return self._draft != self._saved

    @Property("QVariantList", notify=changed)
    def targetLanguages(self):
        choices = [{"label": label, "value": value} for label, value in TARGET_LANGUAGES]
        # Existing JSON can contain any natural-language name. Keep it selectable
        # without silently normalizing it or dropping it when another page edits.
        for data in (self._saved, self._draft):
            value = data["translate"]["target_language"]
            if value and not any(item["value"] == value for item in choices):
                choices.append({"label": value, "value": value})
        return choices

    @Slot(str, "QVariant")
    def setValue(self, path, value):
        parts = path.split(".")
        obj = self._draft
        for part in parts[:-1]:
            if part not in obj or not isinstance(obj[part], dict):
                return
            obj = obj[part]
        key = parts[-1]
        if key not in obj or isinstance(obj[key], dict):
            return
        try:
            value = type(obj[key])(value)
        except (TypeError, ValueError, OverflowError):
            return
        if obj[key] != value:
            obj[key] = value
            self._errors.pop(path, None)
            self.changed.emit()

    @Slot()
    def discard(self):
        self._draft = deepcopy(self._saved)
        self._errors = {}
        self.changed.emit()

    def candidate(self) -> AppConfig | None:
        data = deepcopy(self._draft)
        for section in (data, data["asr"], data["translate"]):
            for key, value in section.items():
                if isinstance(value, str):
                    section[key] = value.strip()
        cfg = AppConfig.from_dict(data)
        self._errors = validate_config(cfg)
        self.changed.emit()
        return None if self._errors else cfg

    def commit(self, cfg: AppConfig):
        self._saved = asdict(cfg)
        self.discard()

    def sync_font(self, size: int):
        # A direct subtitle shortcut must not later be overwritten by a stale draft.
        self._saved["subtitle"]["font_size"] = size
        self._draft["subtitle"]["font_size"] = size
        self.changed.emit()
