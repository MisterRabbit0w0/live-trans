"""Application actions and presentation state; all state lives on the loop thread."""
from __future__ import annotations

import errno
import logging
import threading
from dataclasses import asdict
from pathlib import Path

from ..audio import get_backend
from ..config import AppConfig, config_dir
from ..record.transcript import records_dir
from . import system
from .models import ModelManager
from .records import RecordManager
from .runtime import RuntimeCoordinator
from .settings import SettingsStore, engine_config, validate_config
from .subtitles import SubtitleBuffer

log = logging.getLogger(__name__)


class AppController:
    def __init__(self, cfg: AppConfig, path: Path | None = None, runtime=None, *,
                 loop, models: ModelManager | None = None,
                 on_change=lambda: None, on_event=lambda name, payload: None):
        self.on_change = on_change
        self.on_event = on_event
        self._loop = loop
        self.cfg = cfg
        self._path = path
        self.settings = SettingsStore(cfg, on_change=self._changed)
        self.subtitles = SubtitleBuffer(cfg.subtitle.max_lines)
        self.models = models or ModelManager(loop, on_change=self._changed)
        self.runtime = runtime or RuntimeCoordinator()
        self.runtime.on_event = lambda g, e: loop.post(self._runtime_event, g, e)

        def _get_current_record_path():
            rec = getattr(self.runtime, "_recorder", None)
            return getattr(rec, "path", None)

        self.records = RecordManager(cfg, loop, _get_current_record_path)
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

    def _changed(self):
        self.on_change()

    def _emit(self, name, payload=None):
        self.on_event(name, payload or {})

    @staticmethod
    def _default_device():
        return {"label": get_backend().default_device_label, "value": ""}

    @property
    def audioHints(self):
        backend = get_backend()
        return {"system": backend.system_hint, "app": backend.app_hint}

    @property
    def state(self):
        return self._state

    @property
    def statusTitle(self):
        trans = getattr(self.cfg.translate, "enabled", True)
        rec = self.cfg.record.enabled
        if self._state == "running":
            if trans and rec:
                return "正在翻译与记录"
            if trans:
                return "正在实时翻译"
            if rec:
                return "正在识别与记录"
            return "正在实时语音识别"
        if self._state == "paused":
            return "已暂停"
        return {
            "idle": "尚未开始",
            "starting": "正在准备运行",
            "stopping": "正在停止",
            "error": "暂时无法开始",
        }[self._state]
    @property
    def statusDetail(self):
        errors = {"audio": "声音处理异常", "asr": "语音识别异常", "translate": "翻译服务暂不可用"}
        if self._stages.get("asr") == "error" \
                and self._stage_errors.get("asr") == "ModelNotDownloaded":
            return "所选识别模型尚未下载，请在语音识别页下载后重试。"
        for stage in ("audio", "asr", "translate"):
            if self._stages.get(stage) == "error":
                return errors[stage] + "，请检查对应设置"
        if self._stages.get("record") == "error":
            return "记录文件无法写入，已停止记录；主流程不受影响。"
        if self._state == "running":
            trans = getattr(self.cfg.translate, "enabled", True)
            rec = self.cfg.record.enabled
            if trans and rec:
                return "原文实时呈现，译文随后补全，并保存本地记录。"
            if trans:
                return "原文实时呈现，译文随后补全。"
            if rec:
                return "实时语音识别中，录制内容已实时存入本地记录。"
            return "实时语音识别中，原文已显示在字幕窗。"
        return {
            "idle": "确认声音来源与功能后，点击开始运行。",
            "starting": "正在加载模型并连接声音来源，请稍候。",
            "paused": "点击继续，即可再次接收声音。",
            "stopping": "正在结束当前处理并释放资源，请稍候。",
            "error": "请检查声音来源和模型配置，然后重试。",
        }[self._state]
    @property
    def busy(self):
        return self._state in ("starting", "stopping") or self._quitting

    @property
    def recording(self):
        return self.cfg.record.enabled and self._state in ("running", "paused") \
            and self._stages.get("record") != "error"

    @property
    def translating(self):
        active = self._state in ("running", "paused")
        return getattr(self.cfg.translate, "enabled", True) and active \
            and self._stages.get("translate") != "error"
    @property
    def subtitleVisible(self):
        return self._subtitle_visible

    @property
    def notice(self):
        return self._notice

    @property
    def noticeIsError(self):
        return self._error

    @property
    def committed(self):
        # Credentials belong only to the settings editor, never to overview bindings.
        data = asdict(self.cfg)
        data["asr"].pop("cloud_api_key")
        data["translate"].pop("api_key")
        return data

    @property
    def sourceLabel(self):
        if self._device and self._state in ("running", "paused"):
            return self._device
        if self.cfg.audio_source_mode == "process":
            return self.cfg.audio_process_name
        return "系统声音"

    @property
    def modelLabel(self):
        a = self.cfg.asr
        if self._model and self._state in ("running", "paused"):
            return self._model if a.backend == "cloud" else f"本地 · {self._model}"
        return a.cloud_model if a.backend == "cloud" else (
            "本地 · 自动选择" if a.model == "auto" else f"本地 · {a.model}"
        )

    @property
    def sourceLanguageLabel(self):
        return {
            "auto": "自动检测", "en": "英语", "ja": "日语", "ko": "韩语",
            "zh": "中文", "ru": "俄语", "es": "西班牙语", "fr": "法语",
            "de": "德语",
        }.get(self.cfg.asr.language, self.cfg.asr.language or "自动检测")

    @property
    def translationModelLabel(self):
        return self.cfg.translate.model

    @property
    def targetLanguageLabel(self):
        return self.cfg.translate.target_language

    @property
    def devices(self):
        return self._devices

    @property
    def processes(self):
        return self._processes

    @property
    def refreshing(self):
        return self._refreshing

    @property
    def discoveryError(self):
        return self._discovery_error

    def snapshot(self) -> dict:
        """Everything the frontend renders, under the former QML property names."""
        return {
            "state": self._state,
            "statusTitle": self.statusTitle,
            "statusDetail": self.statusDetail,
            "busy": self.busy,
            "recording": self.recording,
            "translating": self.translating,
            "translateEnabled": getattr(self.cfg.translate, "enabled", True),
            "recordEnabled": self.cfg.record.enabled,
            "subtitleVisible": self._subtitle_visible,
            "noticeIsError": self._error,
            "committed": self.committed,
            "sourceLabel": self.sourceLabel,
            "modelLabel": self.modelLabel,
            "sourceLanguageLabel": self.sourceLanguageLabel,
            "translationModelLabel": self.translationModelLabel,
            "targetLanguageLabel": self.targetLanguageLabel,
            "devices": self._devices,
            "processes": self._processes,
            "refreshing": self._refreshing,
            "discoveryError": self._discovery_error,
            "audioHints": self.audioHints,
        }

    def startup(self):
        if not self.cfg.ui.silent_start:
            self._emit("showRequested")
        if self.cfg.ui.auto_translate:
            self.start()

    def showControlCenter(self):
        self._emit("showRequested")

    def start(self):
        if self._state not in ("idle", "error") or self._quitting:
            return
        errors = validate_config(self.cfg)
        if errors:
            self._state = "error"
            self._message("当前配置需要完善，请在设置中修改并应用。", True)
            self._emit("notification", {"message": self._notice})
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
        self._changed()

    def togglePause(self):
        if self._state in ("idle", "error"):
            self.start()
        elif self._state in ("running", "paused"):
            paused = self._state == "running"
            self.runtime.pause(paused)
            self._state = "paused" if paused else "running"
            self._changed()

    def stop(self):
        if self._state in ("idle", "stopping"):
            return
        self._state = "stopping"
        self._stages = {}
        self._generation = self.runtime.stop()
        self._changed()

    def toggleSubtitles(self):
        self._subtitle_visible = not self._subtitle_visible
        self._changed()
    def toggleTranslation(self):
        new_val = not getattr(self.cfg.translate, "enabled", True)
        self.cfg.translate.enabled = new_val
        self.settings.setValue("translate.enabled", new_val)
        if self._state in ("running", "paused"):
            self._generation = self.runtime.reconfigure(self.cfg)
        self._changed()
        try:
            self.cfg.save(self._path)
        except OSError:
            pass

    def toggleRecord(self):
        new_val = not self.cfg.record.enabled
        self.cfg.record.enabled = new_val
        self.settings.setValue("record.enabled", new_val)
        if self._state in ("running", "paused"):
            self._generation = self.runtime.reconfigure(self.cfg)
        self._changed()
        try:
            self.cfg.save(self._path)
        except OSError:
            pass

    def applySettings(self):
        if self.busy or not self.settings.dirty:
            return
        candidate = self.settings.candidate()
        if candidate is None:
            self._message("请检查标记的设置项，再次应用。", True)
            self._emit("validationFailed", {"path": next(iter(self.settings.errors))})
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
        self._emit("configApplied")
        self._message("设置已保存。")
        if not was_active or before == after:
            return
        if before["transcribe"] != after["transcribe"]:
            self._restarting = True
            self._begin_session(was_paused, resume=True)
        else:
            self.runtime.reconfigure(candidate)
            self._message("设置已保存并应用。")

    def adjustFont(self, delta):
        size = max(10, min(48, self.cfg.subtitle.font_size + delta))
        self.cfg.subtitle.font_size = size
        previous_saved = self.settings.sync_font(size)
        self._changed()
        try:
            self.cfg.save(self._path)
        except OSError:
            self.settings.restore_font_snapshot(previous_saved)
            self._font_save_previous = previous_saved
            self._message("字号已调整，但暂时无法保存到配置文件。", True)
        else:
            self._font_save_previous = None

    def discardSettings(self):
        self.settings.discard()
        if self._font_save_previous is not None:
            self.cfg.subtitle.font_size = self._font_save_previous
            self._font_save_previous = None
            self._changed()

    def dismissNotice(self):
        self._message("")

    def _message(self, message, error=False):
        self._notice, self._error = message, error
        self._changed()

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
                self._emit("quitReady")
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
            self._emit("notification", {"message": self._notice})
        self._changed()

    def refreshDevices(self):
        if self._refreshing:
            return
        self._refreshing = True
        self._changed()
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
        self._loop.post(self._on_devices, devices, processes, "；".join(errors))

    def _on_devices(self, devices, processes, error):
        self._devices = [self._default_device()] + devices
        if self.cfg.audio_device not in [d["value"] for d in self._devices]:
            self._devices.append({"label": "已保存的设备（当前不可用）",
                                  "value": self.cfg.audio_device})
        self._processes = processes
        self._refreshing = False
        self._discovery_error = error
        self._changed()

    def openLogDirectory(self):
        system.open_directory(config_dir())

    def openRecordDirectory(self):
        directory = records_dir()
        try:
            directory.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            log.warning("记录目录不可用 (%s)", type(error).__name__)
            self._message("无法打开记录文件夹。", True)
            return
        system.open_directory(directory)

    def requestQuit(self):
        if self.settings.dirty:
            self._emit("showRequested")
            self._emit("quitConfirmationRequested")
        else:
            self.confirmQuit()

    def confirmQuit(self):
        if self._quitting:
            return
        self._quitting = True
        self._state = "stopping"
        self._generation = self.runtime.stop()
        self._changed()

    def close(self):
        self.models.close()
        self.runtime.close()
