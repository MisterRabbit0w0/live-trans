"""Newline-delimited JSON-RPC 2.0 bridge between the Tauri shell and the core.

Requests arrive on stdin (one object per line) and are dispatched on the
``Loop`` thread; responses and notifications are written to a dedicated
protocol stream so stray stdout output can never corrupt them.
"""
from __future__ import annotations

import argparse
import inspect
import io
import json
import logging
import os
import sys
import threading
from pathlib import Path

from ..config import AppConfig, config_dir
from .controller import AppController
from .loop import Loop
from .runtime import RuntimeCoordinator

log = logging.getLogger(__name__)

PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603

CLOSE_WATCHDOG_S = 10.0


def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(config_dir() / "livetrans.log", encoding="utf-8"),
        ],
    )


class Server:
    """Dispatches requests on the loop thread and coalesces state pushes.

    ``controller_factory(on_change, on_event)`` builds the ``AppController``;
    ``reader`` is a binary line source (``sys.stdin.buffer`` in production) and
    ``writer`` a text sink (a ``TextIO`` over the duplicated stdout fd).
    """

    def __init__(self, loop: Loop, controller_factory, reader, writer):
        self._loop = loop
        self._reader = reader
        self._writer = writer
        self._write_lock = threading.Lock()
        self._state_dirty = self._state_scheduled = False
        self._subtitles_dirty = self._subtitles_scheduled = False
        self._closed = False
        self.controller = controller_factory(self._state_changed, self._on_event)
        self.controller.subtitles.on_change = self._subtitles_changed
        app = self.controller
        self._methods = {
            "app.snapshot": self._snapshot,
            "app.startup": app.startup,
            "app.start": app.start,
            "app.togglePause": app.togglePause,
            "app.stop": app.stop,
            "app.toggleSubtitles": app.toggleSubtitles,
            "app.toggleTranslation": app.toggleTranslation,
            "app.toggleRecord": app.toggleRecord,
            "app.applySettings": app.applySettings,
            "app.discardSettings": app.discardSettings,
            "app.adjustFont": app.adjustFont,
            "app.dismissNotice": app.dismissNotice,
            "app.refreshDevices": app.refreshDevices,
            "app.openLogDirectory": app.openLogDirectory,
            "app.openRecordDirectory": app.openRecordDirectory,
            "app.requestQuit": app.requestQuit,
            "app.confirmQuit": app.confirmQuit,
            "app.shutdown": self._shutdown,
            "settings.set": app.settings.setValue,
            "models.refresh": app.models.refresh,
            "models.download": app.models.download,
            "models.remove": app.models.remove,
            "models.cancel": app.models.cancel,
            "models.openDirectory": app.models.openDirectory,
            "records.list": app.records.list_records,
            "records.get": app.records.get_record,
            "records.delete": app.records.delete_record,
            "records.summarize": app.records.summarize_record,
            "records.export": app.records.export_record,
        }

    # ----- transport -----------------------------------------------------

    def run(self):
        """Read requests until stdin EOF or a shutdown request, then return."""
        threading.Thread(target=self._read, name="livetrans-stdio", daemon=True).start()
        self._loop.run()

    def _read(self):
        try:
            for line in self._reader:
                if line.strip():
                    self._loop.post(self._dispatch, line)
        except (OSError, ValueError):
            pass  # a closed reader means the shell is gone: same as EOF
        finally:
            self._loop.post(self._eof)

    def _send(self, message: dict):
        line = json.dumps(message, ensure_ascii=False) + "\n"
        with self._write_lock:
            self._writer.write(line)
            self._writer.flush()

    def _respond(self, request_id, result=None, error=None):
        message = {"jsonrpc": "2.0", "id": request_id}
        if error is None:
            message["result"] = result
        else:
            message["error"] = error
        self._send(message)

    # ----- dispatch ------------------------------------------------------

    def _dispatch(self, line: bytes):
        try:
            request = json.loads(line)
        except ValueError:
            self._respond(None, error={"code": PARSE_ERROR, "message": "Parse error"})
            return
        has_id = isinstance(request, dict) and "id" in request
        request_id = request.get("id") if has_id else None
        if not isinstance(request, dict) or not isinstance(request.get("method"), str):
            if not isinstance(request, dict) or has_id:
                self._respond(request_id,
                              error={"code": INVALID_REQUEST, "message": "Invalid request"})
            return
        method = self._methods.get(request["method"])
        if method is None:
            if has_id:
                self._respond(request_id,
                              error={"code": METHOD_NOT_FOUND, "message": "Method not found"})
            return
        params = request.get("params")
        if params is None:
            params = {}
        if not isinstance(params, dict):
            if has_id:
                self._respond(request_id,
                              error={"code": INVALID_PARAMS,
                                     "message": "Params must be an object"})
            return
        try:
            inspect.signature(method).bind(**params)
        except TypeError:
            if has_id:
                self._respond(request_id,
                              error={"code": INVALID_PARAMS, "message": "Invalid params"})
            return
        try:
            result = method(**params)
        except Exception as error:
            log.exception("方法 %s 执行失败", request["method"])
            if has_id:
                self._respond(request_id,
                              error={"code": INTERNAL_ERROR, "message": type(error).__name__})
        else:
            if has_id:
                self._respond(request_id, result=result)
        if self._closed:
            self._loop.stop()

    def _state_params(self):
        return {"app": self.controller.snapshot(),
                "settings": self.controller.settings.snapshot(),
                "models": self.controller.models.snapshot()}

    def _snapshot(self):
        return {"state": self._state_params(),
                "subtitles": self.controller.subtitles.rows()}

    # ----- notifications --------------------------------------------------

    def _state_changed(self):
        self._state_dirty = True
        if not self._state_scheduled:
            self._state_scheduled = True
            self._loop.post(self._flush_state)

    def _flush_state(self):
        self._state_scheduled = False
        if not self._state_dirty or self._closed:
            return
        self._state_dirty = False
        self._send({"jsonrpc": "2.0", "method": "state", "params": self._state_params()})

    def _subtitles_changed(self):
        self._subtitles_dirty = True
        if not self._subtitles_scheduled:
            self._subtitles_scheduled = True
            self._loop.post(self._flush_subtitles)

    def _flush_subtitles(self):
        self._subtitles_scheduled = False
        if not self._subtitles_dirty or self._closed:
            return
        self._subtitles_dirty = False
        self._send({"jsonrpc": "2.0", "method": "subtitles",
                    "params": {"entries": self.controller.subtitles.rows()}})

    def _on_event(self, name, payload):
        self._send({"jsonrpc": "2.0", "method": "event",
                    "params": {"name": name, "payload": payload}})
        if name == "quitReady":
            self._close()
            self._loop.stop()

    # ----- shutdown --------------------------------------------------------

    def _shutdown(self):
        """``app.shutdown`` method: close, then the response and exit follow."""
        self._close()

    def _eof(self):
        self._close()
        self._loop.stop()

    def _close(self):
        if self._closed:
            return
        self._closed = True
        watchdog = threading.Timer(CLOSE_WATCHDOG_S, os._exit, args=(0,))
        watchdog.daemon = True
        watchdog.start()
        try:
            self.controller.close()
        except Exception:
            log.exception("关闭核心组件失败")
        finally:
            watchdog.cancel()


def main(argv=None):
    parser = argparse.ArgumentParser(prog="livetrans-core", description=__doc__)
    parser.add_argument("--config", type=Path,
                        help="配置文件路径（默认为用户配置目录下的 config.json）")
    parser.add_argument("--preview", action="store_true",
                        help="使用模拟会话与模拟设备，不触碰音频/模型/网络")
    args = parser.parse_args(argv)

    # Reserve fd 1 for the protocol, then demote stdout so stray prints and
    # C-library writes land on stderr instead of corrupting the stream.
    proto_fd = os.dup(1)
    os.dup2(2, 1)
    sys.stdout = sys.stderr
    writer = os.fdopen(proto_fd, "w", encoding="utf-8", newline="")
    try:
        setup_logging()
        cfg = AppConfig.load(args.config)
        loop = Loop()
        if args.preview:
            from . import controller as controller_module
            from .preview import PreviewBackend, PreviewPipeline

            controller_module.get_backend = lambda: PreviewBackend()
            factory = PreviewPipeline
        else:
            from ..session import Session

            factory = Session
        runtime = RuntimeCoordinator(factory)

        def make_controller(on_change, on_event):
            return AppController(cfg, args.config, runtime, loop=loop,
                                 on_change=on_change, on_event=on_event)

        # pythonw / a detached process may have no stdin at all; an empty stream
        # is just an immediate EOF and the core exits cleanly.
        reader = sys.stdin.buffer if sys.stdin is not None else io.BytesIO()
        Server(loop, make_controller, reader, writer).run()
        writer.flush()
        os._exit(0)
    except Exception:
        log.exception("核心进程异常退出")
        return 1
