"""设置面板：ASR/翻译后端、语言、字幕样式。"""
from __future__ import annotations

from typing import Callable

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QLineEdit,
    QSpinBox,
    QVBoxLayout,
)

from ..audio.capture import list_loopback_devices
from ..config import AppConfig

LANGUAGES = [
    ("自动检测", "auto"),
    ("英语", "en"),
    ("日语", "ja"),
    ("韩语", "ko"),
    ("俄语", "ru"),
    ("西班牙语", "es"),
    ("法语", "fr"),
    ("德语", "de"),
]
LOCAL_MODELS = ["auto", "large-v3-turbo", "large-v3", "medium", "small", "base"]


class SettingsDialog(QDialog):
    def __init__(self, cfg: AppConfig, on_saved: Callable[[], None], parent=None):
        super().__init__(parent)
        self.setWindowTitle("LiveTrans 设置")
        self._cfg = cfg
        self._on_saved = on_saved
        root = QVBoxLayout(self)

        # --- 声音来源 ---
        audio_box = QGroupBox("声音来源")
        audio_form = QFormLayout(audio_box)

        self.audio_mode = QComboBox()
        self.audio_mode.addItem("整个系统（输出设备环回）", "system")
        self.audio_mode.addItem("指定软件（只捕获该进程的声音）", "process")
        self.audio_mode.setCurrentIndex(0 if cfg.audio_source_mode == "system" else 1)
        audio_form.addRow("捕获模式", self.audio_mode)

        self.audio_device = QComboBox()
        self.audio_device.addItem("默认输出设备（自动）", -1)
        try:
            for dev in list_loopback_devices():
                self.audio_device.addItem(dev["name"], int(dev["index"]))
        except Exception:
            pass
        idx = self.audio_device.findData(cfg.audio_device_index)
        self.audio_device.setCurrentIndex(idx if idx >= 0 else 0)
        audio_form.addRow("捕获设备", self.audio_device)

        self.audio_process = QComboBox()
        self.audio_process.setEditable(True)  # 可手动输入进程名
        try:
            from ..audio.process_capture import list_audio_processes

            seen_names = set()
            procs = sorted(list_audio_processes(), key=lambda p: not p[2])  # 活跃优先
            for _pid, name, active in procs:
                if name not in seen_names:
                    seen_names.add(name)
                    self.audio_process.addItem(
                        f"{name}{'（发声中）' if active else ''}", name
                    )
        except Exception:
            pass
        self.audio_process.setCurrentText(cfg.audio_process_name)
        audio_form.addRow("目标软件", self.audio_process)

        def _update_audio_rows() -> None:
            is_process = self.audio_mode.currentData() == "process"
            self.audio_device.setEnabled(not is_process)
            self.audio_process.setEnabled(is_process)

        self.audio_mode.currentIndexChanged.connect(_update_audio_rows)
        _update_audio_rows()
        root.addWidget(audio_box)

        # --- 语音识别 ---
        asr_box = QGroupBox("语音识别")
        asr_form = QFormLayout(asr_box)
        self.asr_backend = QComboBox()
        self.asr_backend.addItem("本地 (faster-whisper)", "local")
        self.asr_backend.addItem("云端 (OpenAI 兼容)", "cloud")
        self.asr_backend.setCurrentIndex(0 if cfg.asr.backend == "local" else 1)
        asr_form.addRow("后端", self.asr_backend)

        self.asr_language = QComboBox()
        for label, code in LANGUAGES:
            self.asr_language.addItem(label, code)
        idx = next((i for i, (_, c) in enumerate(LANGUAGES) if c == cfg.asr.language), 0)
        self.asr_language.setCurrentIndex(idx)
        asr_form.addRow("源语言", self.asr_language)

        self.asr_model = QComboBox()
        self.asr_model.setEditable(True)
        self.asr_model.addItems(LOCAL_MODELS)
        self.asr_model.setCurrentText(cfg.asr.model)
        asr_form.addRow("本地模型", self.asr_model)

        self.asr_cloud_url = QLineEdit(cfg.asr.cloud_base_url)
        asr_form.addRow("云端 Base URL", self.asr_cloud_url)
        self.asr_cloud_key = QLineEdit(cfg.asr.cloud_api_key)
        self.asr_cloud_key.setEchoMode(QLineEdit.EchoMode.Password)
        asr_form.addRow("云端 API Key", self.asr_cloud_key)
        self.asr_cloud_model = QLineEdit(cfg.asr.cloud_model)
        asr_form.addRow("云端模型", self.asr_cloud_model)

        self.vad_silence = QSpinBox()
        self.vad_silence.setRange(250, 1000)
        self.vad_silence.setSingleStep(50)
        self.vad_silence.setSuffix(" ms")
        self.vad_silence.setValue(cfg.vad_silence_ms)
        self.vad_silence.setToolTip(
            "停顿多久切出一句。越小字幕越快但句子更碎；\n"
            "建议直播 350~450，日语口播多停顿建议 ≥450"
        )
        asr_form.addRow("切句停顿", self.vad_silence)
        root.addWidget(asr_box)

        # --- 翻译 ---
        tr_box = QGroupBox("翻译（OpenAI 兼容：本地 Ollama 或任意云端）")
        tr_form = QFormLayout(tr_box)
        self.tr_url = QLineEdit(cfg.translate.base_url)
        tr_form.addRow("Base URL", self.tr_url)
        self.tr_key = QLineEdit(cfg.translate.api_key)
        self.tr_key.setEchoMode(QLineEdit.EchoMode.Password)
        tr_form.addRow("API Key", self.tr_key)
        self.tr_model = QLineEdit(cfg.translate.model)
        tr_form.addRow("模型", self.tr_model)
        self.tr_target = QLineEdit(cfg.translate.target_language)
        tr_form.addRow("目标语言", self.tr_target)
        root.addWidget(tr_box)

        # --- 字幕样式 ---
        sub_box = QGroupBox("字幕")
        sub_form = QFormLayout(sub_box)
        self.sub_font = QSpinBox()
        self.sub_font.setRange(10, 48)
        self.sub_font.setValue(cfg.subtitle.font_size)
        sub_form.addRow("字号", self.sub_font)
        self.sub_bilingual = QCheckBox("显示原文（双语）")
        self.sub_bilingual.setChecked(cfg.subtitle.show_original)
        sub_form.addRow(self.sub_bilingual)
        self.sub_lines = QSpinBox()
        self.sub_lines.setRange(1, 10)
        self.sub_lines.setValue(cfg.subtitle.max_lines)
        sub_form.addRow("同屏条数", self.sub_lines)
        self.sub_opacity = QDoubleSpinBox()
        self.sub_opacity.setRange(0.0, 1.0)
        self.sub_opacity.setSingleStep(0.05)
        self.sub_opacity.setValue(cfg.subtitle.opacity)
        sub_form.addRow("背景不透明度", self.sub_opacity)
        self.sub_width = QSpinBox()
        self.sub_width.setRange(300, 2400)
        self.sub_width.setValue(cfg.subtitle.width)
        sub_form.addRow("宽度(px)", self.sub_width)
        root.addWidget(sub_box)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _save(self) -> None:
        c = self._cfg
        c.audio_source_mode = self.audio_mode.currentData()
        c.audio_device_index = self.audio_device.currentData()
        # 列表项显示文本带"（发声中）"标记，data 才是纯进程名；手动输入时用文本
        idx = self.audio_process.currentIndex()
        if idx >= 0 and self.audio_process.itemText(idx) == self.audio_process.currentText():
            c.audio_process_name = self.audio_process.itemData(idx)
        else:
            c.audio_process_name = self.audio_process.currentText().strip()
        c.vad_silence_ms = self.vad_silence.value()
        c.asr.backend = self.asr_backend.currentData()
        c.asr.language = self.asr_language.currentData()
        c.asr.model = self.asr_model.currentText().strip() or "auto"
        c.asr.cloud_base_url = self.asr_cloud_url.text().strip()
        c.asr.cloud_api_key = self.asr_cloud_key.text().strip()
        c.asr.cloud_model = self.asr_cloud_model.text().strip()
        c.translate.base_url = self.tr_url.text().strip()
        c.translate.api_key = self.tr_key.text().strip()
        c.translate.model = self.tr_model.text().strip()
        c.translate.target_language = self.tr_target.text().strip() or "中文"
        c.subtitle.font_size = self.sub_font.value()
        c.subtitle.show_original = self.sub_bilingual.isChecked()
        c.subtitle.max_lines = self.sub_lines.value()
        c.subtitle.opacity = self.sub_opacity.value()
        c.subtitle.width = self.sub_width.value()
        c.save()
        self.accept()
        self._on_saved()
