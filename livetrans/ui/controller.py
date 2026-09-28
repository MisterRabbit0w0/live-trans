"""Application actions and presentation state; all properties live on the GUI thread."""
from __future__ import annotations

import errno
import logging
import threading
from dataclasses import asdict
from pathlib import Path

from PySide6.QtCore import Property, QObject, QUrl, Signal, Slot
from PySide6.QtGui import QDesktopServices

from ..audio import get_backend
from ..config import AppConfig, config_dir
from ..record.transcript import records_dir
from .models import ModelManager
from .runtime import RuntimeCoordinator
from .settings import SettingsStore, engine_config, validate_config
from .subtitle_model import SubtitleModel

log = logging.getLogger(__name__)


class AppController(QObject):
    changed = Signal()
    showRequested = Signal()
    quitConfirmationRequested = Signal()
    quitReady = Signal()
    notification = Signal(str)
    configApplied = Signal(object)
    validationFailed = Signal(str)
    _devicesReady = Signal(object, object, str)

    def __init__(self, cfg: AppConfig, path: Path | None = None, runtime=None, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self._path = path
        self.settings = SettingsStore(cfg, self)
        self.subtitles = SubtitleModel(cfg.subtitle.max_lines, self)
        self.models = ModelManager(parent=self)
        self.runtime = runtime or RuntimeCoordinator(parent=self)
        self.runtime.event.connect(self._runtime_event)
        self._generation = 0
        self._state = "idle"
        self._subtitle_visible = False
        self._stages = {}
        self._stage_errors = {}
        self._notice = ""
        self._error = False
        self._device = ""
        self._model = ""
        self._restarting = False
        self._quitting = False
        self._font_save_previous: int | None = None
        self._devices = [self._default_device()]
        self._processes = []
        self._refreshing = False
        self._discovery_error = ""
        self._devicesReady.connect(self._on_devices)

    @staticmethod
    def _default_device():
        return {"label": get_backend().default_device_label, "value": ""}

    @Property("QVariantMap", constant=True)
    def audioHints(self):
        backend = get_backend()
        return {"system": backend.system_hint, "app": backend.app_hint}

    @Property(str, notify=changed)
    def state(self):
        return self._state

    @Property(str, notify=changed)
    def statusTitle(self):
        return {
            "idle": "尚未开始", "starting": "正在准备翻译",
            "running": "正在翻译", "paused": "翻译已暂停",
            "stopping": "正在停止", "error": "暂时无法开始",
        }[self._state]

    @Property(str, notify=changed)
    def statusDetail(self):
        errors = {"audio": "声音处理异常", "asr": "语音识别异常", "translate": "翻译服务暂不可用"}
        if self._stages.get("asr") == "error" \
                and self._stage_errors.get("asr") == "ModelNotDownloaded":
            return "所选识别模型尚未下载，请在语音识别页下载后重试。"
        for stage in ("audio", "asr", "translate"):
            if self._stages.get(stage) == "error":
                return errors[stage] + "，请检查对应设置"
        if self._stages.get("record") == "error":
            return "记录文件无法写入，已停止记录；翻译不受影响。"
        return {
            "idle": "确认声音来源和模型后，点击开始翻译。",
            "starting": "正在加载模型并连接声音来源，请稍候。",
            "running": "原文实时呈现，译文随后补全。",
            "paused": "点击继续，即可再次接收声音。",
            "stopping": "正在结束当前处理并释放资源，请稍候。",
            "error": "请检查声音来源和模型配置，然后重试。",
        }[self._state]

    @Property(bool, notify=changed)
    def busy(self):
        return self._state in ("starting", "stopping") or self._quitting

    @Property(bool, notify=changed)
    def recording(self):
        return self.cfg.record.enabled and self._state in ("running", "paused") \
            and self._stages.get("record") != "error"

    @Property(bool, notify=changed)
    def subtitleVisible(self):
        return self._subtitle_visible

    @Property(str, notify=changed)
    def notice(self):
        return self._notice

    @Property(bool, notify=changed)
    def noticeIsError(self):
        return self._error

    @Property("QVariantMap", notify=changed)
    def committed(self):
        # Credentials belong only to the settings editor, never to overview bindings.
        data = asdict(self.cfg)
        data["asr"].pop("cloud_api_key")
        data["translate"].pop("api_key")
        return data

    @Property(str, notify=changed)
    def sourceLabel(self):
        if self._device and self._state in ("running", "paused"):
            return self._device
        if self.cfg.audio_source_mode == "process":
            return self.cfg.audio_process_name
        return "系统声音"

    @Property(str, notify=changed)
    def modelLabel(self):
        a = self.cfg.asr
        if self._model and self._state in ("running", "paused"):
            return self._model if a.backend == "cloud" else f"本地 · {self._model}"
        return a.cloud_model if a.backend == "cloud" else (
            "本地 · 自动选择" if a.model == "auto" else f"本地 · {a.model}"
        )

    @Property(str, notify=changed)
    def sourceLanguageLabel(self):
        return {
            "auto": "自动检测", "en": "英语", "ja": "日语", "ko": "韩语",
            "zh": "中文", "ru": "俄语", "es": "西班牙语", "fr": "法语",
            "de": "德语",
        }.get(self.cfg.asr.language, self.cfg.asr.language or "自动检测")

    @Property(str, notify=changed)
    def translationModelLabel(self):
        return self.cfg.translate.model

    @Property(str, notify=changed)
    def targetLanguageLabel(self):
        return self.cfg.translate.target_language

    @Property("QVariantList", notify=changed)
    def devices(self):
        return self._devices

    @Property("QVariantList", notify=changed)
    def processes(self):
        return self._processes

    @Property(bool, notify=changed)
    def refreshing(self):
        return self._refreshing

    @Property(str, notify=changed)
    def discoveryError(self):
        return self._discovery_error

    def startup(self):
        if not self.cfg.ui.silent_start:
            self.showRequested.emit()
        if self.cfg.ui.auto_translate:
            self.start()

    @Slot()
    def showControlCenter(self):
        self.showRequested.emit()

    @Slot()
    def start(self):
        if self._state not in ("idle", "error") or self._quitting:
            return
        errors = validate_config(self.cfg)
        if errors:
            self._state = "error"
            self._message("当前配置需要完善，请在设置中修改并应用。", True)
            self.notification.emit(self._notice)
            return
        self._begin_session(False)

    def _begin_session(self, paused, resume=False):
        self._state = "starting"
        self._stages = {}
        self._stage_errors = {}
        self._device = ""
        self._model = ""
        self.subtitles.clear()
        self._subtitle_visible = True
        self._generation = self.runtime.start(self.cfg, paused, resume)
        self.changed.emit()

    @Slot()
    def togglePause(self):
        if self._state in ("idle", "error"):
            self.start()
        elif self._state in ("running", "paused"):
            paused = self._state == "running"
            self.runtime.pause(paused)
            self._state = "paused" if paused else "running"
            self.changed.emit()

    @Slot()
    def stop(self):
        if self._state in ("idle", "stopping"):
            return
        self._state = "stopping"
        self._stages = {}
        self._generation = self.runtime.stop()
        self.changed.emit()

    @Slot()
    def toggleSubtitles(self):
        self._subtitle_visible = not self._subtitle_visible
        self.changed.emit()

    @Slot()
    def applySettings(self):
        if self.busy or not self.settings.dirty:
            return
        candidate = self.settings.candidate()
        if candidate is None:
            self._message("请检查标记的设置项，再次应用。", True)
            self.validationFailed.emit(next(iter(self.settings.errors)))
            return
        try:
            candidate.save(self._path)
        except OSError as error:
            log.warning("配置写入失败 (%s)", type(error).__name__)
            reason = "配置目录不可写" if isinstance(error, PermissionError) else {
                errno.ENOSPC: "磁盘空间不足", errno.ENOENT: "配置目录不可用",
                errno.EROFS: "配置目录为只读", errno.ENAMETOOLONG: "配置路径过长",
            }.get(error.errno, "文件系统写入失败")
            self._message(f"无法保存配置：{reason}。修改已保留。", True)
            return
        before, after = engine_config(self.cfg), engine_config(candidate)
        was_paused = self._state == "paused"
        was_active = self._state in ("running", "paused")
        self.cfg = candidate
        self._font_save_previous = None
        self.settings.commit(candidate)
        self.subtitles.set_limit(candidate.subtitle.max_lines)
        self.configApplied.emit(candidate)
        self._message("设置已保存。")
        if not was_active or before == after:
            return
        if before["transcribe"] != after["transcribe"]:
            self._restarting = True
            self._begin_session(was_paused, resume=True)
        else:
            self.runtime.reconfigure(candidate)
            self._message("设置已保存并应用。")

    @Slot(int)
    def adjustFont(self, delta):
        size = max(10, min(48, self.cfg.subtitle.font_size + delta))
        self.cfg.subtitle.font_size = size
        previous_saved = self.settings.sync_font(size)
        self.changed.emit()
        try:
            self.cfg.save(self._path)
        except OSError:
            self.settings.restore_font_snapshot(previous_saved)
            self._font_save_previous = previous_saved
            self._message("字号已调整，但暂时无法保存到配置文件。", True)
        else:
            self._font_save_previous = None

    @Slot()
    def discardSettings(self):
        self.settings.discard()
        if self._font_save_previous is not None:
            self.cfg.subtitle.font_size = self._font_save_previous
            self._font_save_previous = None
            self.changed.emit()

    @Slot()
    def dismissNotice(self):
        self._message("")

    def _message(self, message, error=False):
        self._notice, self._error = message, error
        self.changed.emit()

    @Slot(int, object)
    def _runtime_event(self, generation, event):
        if generation != self._generation:
            return
        kind = event["kind"]
        if kind == "entry":
            self.subtitles.add(event["id"], event["original"], event["language"])
            return
        if kind == "translation":
            self.subtitles.translate(event["id"], event["translation"])
            return
        if kind == "stage":
            stage, error = event["stage"], event.get("error")
            if self._stages.get(stage) == event["status"] \
                    and self._stage_errors.get(stage) == error:
                return
            self._stages[stage] = event["status"]
            self._stage_errors[stage] = error
        elif kind == "started":
            self._state = "paused" if event.get("paused") else "running"
            self._device = event.get("device", "")
            self._model = event.get("model", "")
            self._notice = "设置已保存并应用。" if self._restarting else ""
            self._error = self._restarting = False
        elif kind == "stopped":
            self._state = "idle"
            self._subtitle_visible = False
            if self._quitting:
                self.quitReady.emit()
        elif kind == "failed":
            self._state = "error"
            self._quitting = False
            prefix = "设置已保存，启动失败。" if self._restarting else "操作未完成。"
            if event.get("reason") == "shutdown_pending":
                detail = "上一会话仍在停止，尚未启动新会话。请稍后重试。"
            elif event.get("error") == "ModelNotDownloaded":
                detail = "所选识别模型尚未下载，请在「语音识别」页下载。"
            else:
                detail = "请检查声音来源、模型或服务配置，然后重试。"
            self._notice = prefix + detail
            self._error = True
            self._restarting = False
            self.notification.emit(self._notice)
        self.changed.emit()

    @Slot()
    def refreshDevices(self):
        if self._refreshing:
            return
        self._refreshing = True
        self.changed.emit()
        threading.Thread(target=self._discover, name="livetrans-devices", daemon=True).start()

    def _discover(self):
        devices, processes, errors = [], [], []
        backend = get_backend()
        try:
            devices = [{"label": d.label, "value": d.id} for d in backend.list_devices()]
        except Exception:
            log.warning("刷新输出设备失败", exc_info=True)
            errors.append("无法刷新输出设备")
        try:
            processes = [{"label": a.label + (" · 发声中" if a.active else ""), "value": a.name}
                         for a in backend.list_apps()]
        except Exception:
            log.warning("刷新软件列表失败", exc_info=True)
            errors.append("无法刷新软件列表，可直接输入进程名")
        self._devicesReady.emit(devices, processes, "；".join(errors))

    @Slot(object, object, str)
    def _on_devices(self, devices, processes, error):
        self._devices = [self._default_device()] + devices
        if self.cfg.audio_device not in [d["value"] for d in self._devices]:
            self._devices.append({"label": "已保存的设备（当前不可用）",
                                  "value": self.cfg.audio_device})
        self._processes = processes
        self._refreshing = False
        self._discovery_error = error
        self.changed.emit()

    @Slot()
    def openLogDirectory(self):
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(config_dir())))

    @Slot()
    def openRecordDirectory(self):
        directory = records_dir()
        try:
            directory.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            log.warning("记录目录不可用 (%s)", type(error).__name__)
            self._message("无法打开记录文件夹。", True)
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(directory)))

    @Slot()
    def requestQuit(self):
        if self.settings.dirty:
            self.showRequested.emit()
            self.quitConfirmationRequested.emit()
        else:
            self.confirmQuit()

    @Slot()
    def confirmQuit(self):
        if self._quitting:
            return
        self._quitting = True
        self._state = "stopping"
        self._generation = self.runtime.stop()
        self.changed.emit()

    def close(self):
        self.models.close()
        self.runtime.close()
