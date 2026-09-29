"""Start and talk to a model worker process.

The worker runs either the app's own interpreter (``runtime=""``) or an
external Python environment chosen by the user, so heavy or GPU-specific
packages never have to live in the GUI process. A crashed or hung worker is
killed and restarted; the GUI never shares its fate.
"""
from __future__ import annotations

import logging
import os
import queue
import subprocess
import sys
import threading
from collections.abc import Callable
from pathlib import Path

from ..config import config_dir
from .protocol import PROTOCOL_VERSION, ProtocolError, read_frame, write_frame

log = logging.getLogger(__name__)

WORKER_FLAG = "--livetrans-worker"
HELLO_TIMEOUT = 60.0  # interpreter start-up plus imports, on a slow disk
# Download progress travels as frames; console bars would only fill worker.log.
_WORKER_ENV = {"PYTHONIOENCODING": "utf-8", "PYTHONUNBUFFERED": "1",
               "HF_HUB_DISABLE_PROGRESS_BARS": "1"}


class WorkerError(RuntimeError):
    """The worker reported a failure or stopped answering."""

    def __init__(self, message, kind="WorkerError"):
        super().__init__(message)
        self.kind = kind


def source_root() -> Path:
    """Directory that contains ``livetrans/worker`` as plain source files."""
    bundle = getattr(sys, "_MEIPASS", None)
    if bundle is not None:
        return Path(bundle) / "runtime-src"
    return Path(__file__).resolve().parents[2]


def resolve_interpreter(runtime: str) -> Path:
    """Accept an interpreter path or an environment directory (venv / conda / embedded)."""
    # Absolute: the worker starts in ``source_root()``, not the caller's directory.
    path = Path(runtime).expanduser().absolute()
    if path.is_dir():
        for candidate in ("Scripts/python.exe", "python.exe", "bin/python3", "bin/python"):
            if (path / candidate).is_file():
                return path / candidate
        raise FileNotFoundError(f"{path} 中没有找到 Python 解释器")
    if path.is_file():
        return path
    raise FileNotFoundError(f"运行环境不存在：{path}")


def worker_command(runtime: str = "") -> tuple[list[str], dict]:
    env = dict(os.environ)
    env.update(_WORKER_ENV)
    if not runtime:
        if getattr(sys, "frozen", False):
            return [sys.executable, WORKER_FLAG], env
        env["PYTHONPATH"] = os.pathsep.join(
            p for p in (str(source_root()), os.environ.get("PYTHONPATH", "")) if p)
        return [sys.executable, "-m", "livetrans.worker"], env
    # An external runtime sees only its own packages plus the worker sources.
    for key in list(env):
        if key.startswith(("_PYI", "PYINSTALLER", "PYTHON", "_MEIPASS")) or key == "VIRTUAL_ENV":
            del env[key]
    env.update(_WORKER_ENV, PYTHONPATH=str(source_root()), PYTHONNOUSERSITE="1")
    return [str(resolve_interpreter(runtime)), "-s", "-m", "livetrans.worker"], env


class WorkerProcess:
    """One worker process; ``request`` is serialized, ``kill`` works from any thread."""

    def __init__(self, runtime: str = "",
                 popen: Callable[..., subprocess.Popen] = subprocess.Popen):
        self._runtime = runtime
        self._popen = popen
        self._process = None
        self._replies: queue.Queue = queue.Queue()
        self._lock = threading.Lock()
        self._next_id = 0
        self._log = None
        self.info: dict = {}

    @property
    def alive(self):
        return self._process is not None and self._process.poll() is None

    def start(self):
        args, env = worker_command(self._runtime)
        flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        self._log = open(config_dir() / "worker.log", "ab")
        self._replies = queue.Queue()
        try:
            self._process = self._popen(
                args, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self._log,
                env=env, creationflags=flags, cwd=str(source_root()),
            )
        except OSError:
            self._close_log()
            raise
        threading.Thread(target=self._read, args=(self._process, self._replies),
                         name="livetrans-worker-reader", daemon=True).start()
        hello = self._wait(self._replies, HELLO_TIMEOUT)
        if hello.get("type") != "hello" or hello.get("version") != PROTOCOL_VERSION:
            self.kill()
            raise WorkerError(f"运行环境协议不兼容：{hello}")
        self.info = hello
        log.info("模型进程已启动 (pid %s, Python %s)", hello.get("pid"), hello.get("python"))

    def request(self, header: dict, payload: bytes = b"", timeout: float | None = None,
                on_progress=None) -> dict:
        """``timeout`` bounds each reply frame; progress frames go to ``on_progress``."""
        with self._lock:
            if not self.alive:
                raise WorkerError("模型进程未运行", "WorkerExited")
            self._next_id += 1
            header = dict(header, id=self._next_id)
            try:
                write_frame(self._process.stdin, header, payload)
            except (OSError, ValueError) as error:
                raise WorkerError("模型进程已退出", "WorkerExited") from error
            while True:
                reply = self._wait(self._replies, timeout)
                if reply.get("type") != "progress":
                    break
                if on_progress is not None:
                    on_progress(reply.get("done", 0), reply.get("total", 0))
            if reply.get("type") == "error":
                raise WorkerError(reply.get("message", ""), reply.get("error", "WorkerError"))
            return reply

    def stop(self, timeout=3.0):
        process = self._process
        if process is None:
            return
        if process.poll() is None:
            try:
                write_frame(process.stdin, {"op": "shutdown"})
                process.stdin.close()
            except (OSError, ValueError):
                pass
            try:
                process.wait(timeout)
            except subprocess.TimeoutExpired:
                pass
        self.kill()

    def kill(self):
        process = self._process
        if process is not None:
            if process.poll() is None:
                process.kill()
            try:
                process.wait(5)
            except subprocess.TimeoutExpired:
                log.warning("模型进程 %s 未能结束", process.pid)
            for stream in (process.stdin, process.stdout):
                try:
                    stream.close()
                except (OSError, ValueError):
                    pass
        self._close_log()

    def _close_log(self):
        if self._log is not None:
            self._log.close()
            self._log = None

    def _wait(self, replies, timeout):
        try:
            reply = replies.get(timeout=timeout)
        except queue.Empty:
            self.kill()
            raise WorkerError("模型进程无响应，已结束", "WorkerTimeout") from None
        if reply is None:
            code = self._process.poll() if self._process is not None else None
            raise WorkerError(f"模型进程已退出 (code {code})，详见 worker.log", "WorkerExited")
        return reply

    @staticmethod
    def _read(process, replies):
        try:
            while True:
                header, _ = read_frame(process.stdout)
                replies.put(header)
        except (ProtocolError, OSError, ValueError):
            replies.put(None)
