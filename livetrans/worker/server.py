"""Model worker: owns the speech model and answers frames on stdin/stdout.

Requests, one at a time:

    {"op": "load", "model": ..., "device": ..., "cuda": bool}
        -> {"type": "loaded", "model": ..., "device": ...}
    {"op": "transcribe", "id": n, "language": str|null} + float32 mono 16 kHz
        -> {"type": "result", "id": n, "language": ..., "text": ...}
    {"op": "models", "cuda": bool}
        -> {"type": "models", "dir": ..., "installed": [...], "recommended": ..., ...}
    {"op": "download", "model": ...}
        -> {"type": "progress", "done": bytes, "total": bytes} ... {"type": "downloaded"}
    {"op": "delete", "model": ...} -> {"type": "deleted"}
    {"op": "shutdown"}

Loading only uses models already in the environment; a missing one answers
``{"type": "error", "error": "ModelMissing", "message": <model>}``. Any failed
request answers an error and the worker keeps serving. EOF on stdin (the app
went away) ends it.
"""
from __future__ import annotations

import logging
import os
import sys
import threading

from .protocol import PROTOCOL_VERSION, ProtocolError, read_frame, write_frame

log = logging.getLogger("livetrans.worker")


def _default_engine(model, device, cuda):
    from .engine import WhisperEngine

    return WhisperEngine(model, device, cuda=cuda)


def _claim_stdio():
    """Keep the protocol pipe private; stray native prints go to stderr instead."""
    # Raw descriptors: a windowed frozen build may leave sys.stdin/stdout as None.
    stdin = os.fdopen(os.dup(0), "rb", buffering=0)
    stdout = os.fdopen(os.dup(1), "wb")
    os.dup2(2, 1)
    if sys.stderr is None:
        sys.stderr = os.fdopen(os.dup(2), "w", encoding="utf-8", errors="replace")
    sys.stdout = sys.stderr
    return stdin, stdout


def serve(stdin, stdout, engine_factory=_default_engine, models=None) -> int:
    import numpy as np

    if models is None:
        from . import models
    engine = None
    lock = threading.Lock()  # progress frames come from the download's reporter thread

    def send(header):
        with lock:
            write_frame(stdout, header)

    send({"type": "hello", "version": PROTOCOL_VERSION, "pid": os.getpid(),
          "python": sys.version.split()[0], "models": str(models.models_dir())})
    while True:
        try:
            request, payload = read_frame(stdin)
        except ProtocolError:
            return 0
        op = request.get("op")
        reply = {"id": request.get("id")}
        try:
            if op == "shutdown":
                return 0
            if op == "load":
                engine = None  # release the previous model before loading another
                engine = engine_factory(request.get("model", "auto"),
                                        request.get("device", "auto"),
                                        bool(request.get("cuda", True)))
                reply.update(type="loaded", model=engine.model_name, device=engine.device)
            elif op == "transcribe":
                if engine is None:
                    raise RuntimeError("model not loaded")
                audio = np.frombuffer(payload, dtype=np.float32)
                language, text = engine.transcribe(audio, request.get("language"))
                reply.update(type="result", language=language, text=text)
            elif op == "models":
                reply.update(type="models", **models.listing(bool(request.get("cuda", True))))
            elif op == "download":
                name, request_id = str(request.get("model", "")), reply["id"]

                def progress(done, total, request_id=request_id):
                    send({"id": request_id, "type": "progress", "done": done, "total": total})

                path = models.download(name, progress)
                reply.update(type="downloaded", model=name, path=str(path))
            elif op == "delete":
                models.delete(str(request.get("model", "")))
                reply.update(type="deleted")
            else:
                raise ValueError(f"unknown op {op!r}")
        except models.ModelMissing as missing:
            reply.update(type="error", error="ModelMissing", message=str(missing))
        except Exception as error:
            log.exception("worker request %s failed", op)
            reply.update(type="error", error=type(error).__name__, message=str(error)[:500])
        send(reply)


def main(engine_factory=_default_engine) -> int:
    stdin, stdout = _claim_stdio()
    logging.basicConfig(level=logging.INFO, stream=sys.stderr,
                        format="%(name)s %(levelname)s %(message)s")
    try:
        return serve(stdin, stdout, engine_factory)
    except BrokenPipeError:
        return 0
