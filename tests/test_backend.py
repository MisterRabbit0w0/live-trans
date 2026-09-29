"""Platform audio backends and the out-of-process model runtime, without models or devices."""
from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import tempfile
import textwrap
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from livetrans import audio
from livetrans.app.settings import engine_config, validate_config
from livetrans.asr.whisper_local import LocalWhisper
from livetrans.audio.base import TARGET_RATE, UnsupportedBackend, to_mono_16k
from livetrans.audio.linux import LinuxBackend, ParecCapture, parse_blocks
from livetrans.config import AppConfig
from livetrans.transcriber import build_capture
from livetrans.worker import models
from livetrans.worker.client import WorkerError, WorkerProcess, resolve_interpreter
from livetrans.worker.protocol import ProtocolError, read_frame, write_frame
from livetrans.worker.server import serve

# A worker that echoes the payload size instead of loading faster-whisper.
FAKE_WORKER = textwrap.dedent("""
    import os, sys
    from livetrans.worker import server

    class Engine:
        def __init__(self, model, device, cuda):
            if model == "broken":
                raise ValueError("no such model")
            if model == "absent":
                from livetrans.worker.models import ModelMissing
                raise ModelMissing(model)
            self.model_name, self.device = model if model != "auto" else "small", "cpu"
        def transcribe(self, audio, language):
            if len(audio) == 3:
                os._exit(3)  # simulate a native crash mid-request
            if len(audio) == 7:
                import time
                time.sleep(60)  # simulate a hung model
            return language or "en", f"{len(audio)} samples"

    sys.exit(server.main(lambda m, d, c: Engine(m, d, c)))
""")


def fake_popen(args, **kwargs):
    return subprocess.Popen([sys.executable, "-c", FAKE_WORKER], **kwargs)


class ProtocolTest(unittest.TestCase):
    def test_frames_roundtrip_and_reject_truncation(self):
        stream = io.BytesIO()
        write_frame(stream, {"op": "transcribe", "text": "你好"}, b"\x00\x01")
        write_frame(stream, {"op": "shutdown"})
        stream.seek(0)
        self.assertEqual(read_frame(stream), ({"op": "transcribe", "text": "你好"}, b"\x00\x01"))
        self.assertEqual(read_frame(stream), ({"op": "shutdown"}, b""))
        with self.assertRaises(ProtocolError):
            read_frame(stream)
        truncated = io.BytesIO(stream.getvalue()[:7])
        with self.assertRaises(ProtocolError):
            read_frame(truncated)

    def test_server_reports_errors_and_keeps_serving(self):
        requests = io.BytesIO()
        write_frame(requests, {"op": "transcribe", "id": 1})
        write_frame(requests, {"op": "load", "id": 2, "model": "tiny"})
        write_frame(requests, {"op": "transcribe", "id": 3, "language": "ja"},
                    np.zeros(5, np.float32).tobytes())
        write_frame(requests, {"op": "shutdown"})
        requests.seek(0)
        replies = io.BytesIO()

        class Engine:
            model_name, device = "tiny", "cpu"

            def transcribe(self, audio, language):
                return language, str(len(audio))

        with self.assertLogs("livetrans.worker", "ERROR"):
            self.assertEqual(serve(requests, replies, lambda *a: Engine()), 0)
        replies.seek(0)
        headers = [read_frame(replies)[0] for _ in range(4)]
        self.assertEqual(headers[0]["type"], "hello")
        self.assertEqual((headers[1]["type"], headers[1]["id"]), ("error", 1))
        self.assertEqual(headers[2], {"id": 2, "type": "loaded", "model": "tiny", "device": "cpu"})
        self.assertEqual(headers[3]["text"], "5")
        self.assertEqual(headers[3]["language"], "ja")


class WorkerProcessTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        patcher = patch("livetrans.worker.client.config_dir", return_value=Path(self.tmp.name))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self.tmp.cleanup)

    def factory(self, runtime):
        return WorkerProcess(runtime, popen=fake_popen)

    def test_transcribes_in_a_separate_process(self):
        engine = LocalWhisper("auto", "auto", worker_factory=self.factory)
        try:
            self.assertEqual((engine.model_name, engine.device), ("small", "cpu"))
            result = engine.transcribe(np.zeros(1600, np.float32), "de")
            self.assertEqual((result.language, result.text), ("de", "1600 samples"))
            self.assertNotEqual(engine._worker.info["pid"], threading.get_native_id())
        finally:
            engine.close()
        self.assertIsNone(engine._worker)

    def test_crashed_worker_restarts_then_gives_up(self):
        engine = LocalWhisper("tiny", "cpu", worker_factory=self.factory)
        try:
            first = engine._worker.info["pid"]
            with self.assertLogs("livetrans.asr.whisper_local", "WARNING"), \
                    self.assertRaises(WorkerError) as caught:
                engine.transcribe(np.zeros(3, np.float32))
            self.assertEqual(caught.exception.kind, "WorkerExited")
            # Every restart loaded the model that actually ran, then kept serving.
            with self.assertLogs("livetrans.asr.whisper_local", "WARNING"):
                self.assertEqual(engine.transcribe(np.zeros(4, np.float32)).text, "4 samples")
            self.assertNotEqual(engine._worker.info["pid"], first)
        finally:
            engine.close()

    def test_load_failure_is_reported_and_kills_the_worker(self):
        workers = []

        def factory(runtime):
            workers.append(self.factory(runtime))
            return workers[-1]

        with self.assertRaises(WorkerError) as caught:
            LocalWhisper("broken", "cpu", worker_factory=factory)
        self.assertEqual(caught.exception.kind, "ValueError")
        self.assertFalse(workers[0].alive)

    def test_missing_model_raises_a_download_hint(self):
        from livetrans.asr.whisper_local import ModelNotDownloaded

        with self.assertRaises(ModelNotDownloaded) as caught:
            LocalWhisper("absent", "cpu", worker_factory=self.factory)
        self.assertEqual(caught.exception.model, "absent")

    def test_close_interrupts_a_hung_request(self):
        engine = LocalWhisper("tiny", "cpu", worker_factory=self.factory)
        errors = []

        def transcribe():
            try:
                engine.transcribe(np.zeros(7, np.float32))
            except WorkerError as error:
                errors.append(error.kind)

        thread = threading.Thread(target=transcribe)
        thread.start()
        thread.join(0.5)
        self.assertTrue(thread.is_alive())
        engine.close()
        thread.join(5)
        self.assertFalse(thread.is_alive())
        self.assertEqual(errors, ["WorkerClosed"])

    def test_runtime_accepts_environment_directories(self):
        root = Path(self.tmp.name)
        python = root / "env" / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python3")
        python.parent.mkdir(parents=True)
        python.write_bytes(b"")
        self.assertEqual(resolve_interpreter(str(root / "env")), python.absolute())
        self.assertEqual(resolve_interpreter(str(python)), python.absolute())
        with self.assertRaises(FileNotFoundError):
            resolve_interpreter(str(root / "missing"))
        cfg = AppConfig()
        cfg.asr.runtime = str(root / "missing")
        self.assertIn("asr.runtime", validate_config(cfg))
        cfg.asr.runtime = str(root / "env")
        self.assertNotIn("asr.runtime", validate_config(cfg))


def fake_model(root, name):
    path = models.folder(name, root)
    path.mkdir(parents=True)
    for file in ("config.json", "model.bin", "tokenizer.json"):
        (path / file).write_bytes(b"x" * 10)
    (path / models.MARKER).write_text(json.dumps({"name": name}), "utf-8")
    return path


class FakeHub:
    """Stands in for huggingface_hub: an empty or pre-filled cache, an offline API."""

    def __init__(self, cached=None):
        self.cached = cached
        self.downloads = []
        self.xet_cache = None

    def snapshot_download(self, repo, local_dir=None, allow_patterns=None,
                          local_files_only=False):
        if local_files_only:
            if self.cached is None:
                raise FileNotFoundError(repo)
            return str(self.cached)
        self.downloads.append((repo, Path(local_dir)))
        self.xet_cache = os.environ.get("HF_XET_CACHE")
        for file in ("config.json", "model.bin", "vocabulary.txt"):
            (Path(local_dir) / file).write_bytes(b"y" * 100)
        (Path(local_dir) / ".cache").mkdir(exist_ok=True)
        return local_dir

    def HfApi(self):
        raise OSError("offline")


class ModelStoreTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "models"
        vram = patch("livetrans.worker.models.detect_free_vram_mb", return_value=0)
        vram.start()
        self.addCleanup(vram.stop)

    def test_models_live_in_the_running_environment(self):
        env = Path(self.tmp.name) / "env"
        with patch.object(sys, "prefix", str(env)):
            self.assertEqual(models.models_dir(), env / "livetrans-models")

    def test_loading_never_downloads(self):
        with self.assertRaises(models.ModelMissing) as caught:
            models.select("auto", "auto", root=self.root)
        self.assertEqual(str(caught.exception), "small")
        with self.assertRaises(models.ModelMissing):
            models.select("medium", "cpu", root=self.root)
        # A half-finished download has files but no marker.
        partial = models.folder("small", self.root)
        partial.mkdir(parents=True)
        (partial / "config.json").write_bytes(b"")
        (partial / "model.bin").write_bytes(b"")
        with self.assertRaises(models.ModelMissing):
            models.resolve("small", self.root)

    def test_auto_picks_the_best_installed_model_for_the_hardware(self):
        fake_model(self.root, "base")
        path, name, device, compute = models.select("auto", "auto", root=self.root)
        self.assertEqual((path.name, name, device, compute), ("base", "base", "cpu", "int8"))
        fake_model(self.root, "large-v3-turbo")
        with patch("livetrans.worker.models.detect_free_vram_mb", return_value=8000):
            self.assertEqual(models.select("auto", "auto", root=self.root)[1:],
                             ("large-v3-turbo", "cuda", "float16"))
            # Forcing CPU never picks a large model even when one is installed.
            self.assertEqual(models.select("auto", "cpu", root=self.root)[1], "base")
            self.assertEqual(models.listing(root=self.root)["auto"], "large-v3-turbo")

    def test_explicit_download_into_the_environment(self):
        hub, reports = FakeHub(), []
        with patch.dict(sys.modules, {"huggingface_hub": hub}), \
                patch.dict(os.environ, {}, clear=False):
            path = models.download("Org/custom-ct2", lambda d, t: reports.append((d, t)),
                                   root=self.root)
        self.assertEqual(path, self.root / "Org--custom-ct2")
        self.assertEqual(hub.downloads, [("Org/custom-ct2", path)])
        self.assertEqual(hub.xet_cache, str(path / ".cache" / "xet"))
        self.assertFalse((path / ".cache").exists())
        self.assertTrue(models.is_installed(path))
        self.assertEqual(reports[-1][0], reports[-1][1])
        self.assertEqual([m["name"] for m in models.installed(self.root)], ["Org/custom-ct2"])
        self.assertEqual(models.resolve("Org/custom-ct2", self.root), path)
        models.delete("Org/custom-ct2", self.root)
        self.assertEqual(models.installed(self.root), [])

    def test_existing_hub_cache_is_copied_instead_of_downloaded(self):
        cache = Path(self.tmp.name) / "hub-snapshot"
        cache.mkdir()
        for file in ("config.json", "model.bin"):
            (cache / file).write_bytes(b"z" * 5)
        hub = FakeHub(cached=cache)
        with patch.dict(sys.modules, {"huggingface_hub": hub}):
            path = models.download("small", root=self.root)
        self.assertEqual(hub.downloads, [])
        self.assertEqual((path / "model.bin").read_bytes(), b"z" * 5)
        self.assertTrue(models.is_installed(path))

    def test_invalid_names_are_rejected(self):
        for name in ("", "../escape", "C:/x", "a\\b"):
            with self.assertRaises(ValueError, msg=name):
                models.folder(name, self.root)
        with self.assertRaises(ValueError):
            models.repo_for("not-a-model")

    def test_worker_reports_a_missing_model_by_type(self):
        requests = io.BytesIO()
        write_frame(requests, {"op": "load", "id": 1, "model": "small"})
        requests.seek(0)
        replies = io.BytesIO()

        def factory(model, device, cuda):
            raise models.ModelMissing(model)

        serve(requests, replies, factory)
        replies.seek(0)
        read_frame(replies)  # hello
        reply = read_frame(replies)[0]
        self.assertEqual((reply["error"], reply["message"]), ("ModelMissing", "small"))


class ModelManagerTest(unittest.TestCase):
    def setUp(self):
        from livetrans.app.loop import Loop

        self.loop = Loop()

    def wait(self, manager):
        deadline = time.monotonic() + 5
        while manager.busy and time.monotonic() < deadline:
            self.loop.process_pending(0.005)
            time.sleep(0.005)
        self.assertFalse(manager.busy)

    def test_download_reports_progress_then_lists_the_environment(self):
        from livetrans.app.models import ModelManager

        requests, seen = [], []

        class Worker:
            def __init__(self, runtime):
                self.runtime = runtime

            def start(self):
                pass

            def request(self, header, timeout=None, on_progress=None):
                requests.append((self.runtime, header["op"], header.get("model")))
                if header["op"] == "download":
                    on_progress(50, 100)
                    return {"type": "downloaded"}
                return {"type": "models", "dir": "/env/livetrans-models", "writable": True,
                        "recommended": "small", "auto": "small",
                        "installed": [{"name": "small", "size": 480 << 20}]}

            def stop(self):
                pass

            def kill(self):
                pass

        manager = ModelManager(self.loop, worker_factory=Worker)
        manager.on_change = lambda: seen.append((manager.state, manager.progress))
        manager.download("/env", "small")
        self.assertEqual(manager.state, "downloading")
        self.wait(manager)
        self.assertEqual(requests, [("/env", "download", "small"), ("/env", "models", None)])
        self.assertIn(("downloading", 0.5), seen)
        self.assertTrue(manager.isInstalled("small"))
        self.assertEqual(manager.installed, [{"name": "small", "size": "480 MB"}])
        self.assertEqual((manager.directory, manager.error), ("/env/livetrans-models", ""))

    def test_failures_and_cancel_are_reported(self):
        from livetrans.app.models import ModelManager

        class Worker:
            def __init__(self, runtime):
                pass

            def start(self):
                raise WorkerError("运行环境不存在")

            def stop(self):
                pass

        manager = ModelManager(self.loop, worker_factory=Worker)
        manager.refresh("/missing")
        self.wait(manager)
        self.assertEqual(manager.error, "无法读取模型：运行环境不存在")


class AudioBackendTest(unittest.TestCase):
    def test_platform_selection_is_lazy_and_has_a_fallback(self):
        audio.get_backend.cache_clear()
        self.addCleanup(audio.get_backend.cache_clear)
        with patch.object(sys, "platform", "linux"):
            self.assertIsInstance(audio.get_backend(), LinuxBackend)
        audio.get_backend.cache_clear()
        with patch.object(sys, "platform", "sunos5"):
            backend = audio.get_backend()
        self.assertIsInstance(backend, UnsupportedBackend)
        self.assertEqual(backend.list_devices(), [])
        with self.assertRaises(RuntimeError):
            backend.open_system(lambda chunk: None)

    def test_capture_follows_the_configured_source(self):
        class Backend:
            def open_system(self, on_chunk, device=""):
                return ("system", device)

            def open_app(self, on_chunk, app):
                return ("app", app)

        cfg = AppConfig(audio_device="42")
        with patch("livetrans.transcriber.get_backend", return_value=Backend()):
            self.assertEqual(build_capture(cfg, None), ("system", "42"))
            cfg.audio_source_mode, cfg.audio_process_name = "process", "firefox"
            self.assertEqual(build_capture(cfg, None), ("app", "firefox"))

    def test_downmix_and_resample(self):
        stereo = np.tile(np.array([[1.0, 0.0]], np.float32), (4800, 1)).reshape(-1)
        mono = to_mono_16k(stereo, 48000, 2)
        self.assertEqual((mono.dtype, len(mono)), (np.float32, 1600))
        self.assertTrue(np.allclose(mono, 0.5))
        self.assertEqual(len(to_mono_16k(np.zeros(1, np.float32), 48000, 1)), 0)
        same = np.arange(TARGET_RATE, dtype=np.float32)
        self.assertTrue(np.array_equal(to_mono_16k(same, TARGET_RATE, 1), same))

    def test_legacy_device_index_and_runtime_is_engine_input(self):
        self.assertEqual(AppConfig.from_dict({"audio_device_index": 3}).audio_device, "3")
        self.assertEqual(AppConfig.from_dict({"audio_device_index": -1}).audio_device, "")
        self.assertEqual(AppConfig.from_dict({"audio_device": "x", "audio_device_index": 3})
                         .audio_device, "x")
        cfg = AppConfig()
        before = engine_config(cfg)
        cfg.asr.runtime = "/opt/cuda-env"
        self.assertNotEqual(before["transcribe"], engine_config(cfg)["transcribe"])
        cfg.asr.backend = "cloud"
        self.assertNotIn("runtime", engine_config(cfg)["transcribe"]["asr"])


PACTL_SINKS = """Sink #52
\tState: RUNNING
\tName: alsa_output.pci-0000_00_1f.3.analog-stereo
\tDescription: Built-in Audio Analog Stereo
\tProperties:
\t\tdevice.description = "Built-in Audio Analog Stereo"

Sink #60
\tState: SUSPENDED
\tName: bluez_output.AA_BB.1
\tDescription: Headphones
"""

PACTL_INPUTS = """Sink Input #101
\tDriver: protocol-native.c
\tSink: 52
\tCorked: yes
\tProperties:
\t\tapplication.name = "Firefox"
\t\tapplication.process.binary = "firefox"

Sink Input #107
\tSink: 52
\tCorked: no
\tProperties:
\t\tapplication.name = "Firefox"
\t\tapplication.process.binary = "firefox"

Sink Input #110
\tSink: 60
\tCorked: no
\tProperties:
\t\tapplication.name = "mpv Media Player"
\t\tapplication.process.binary = "mpv"
"""


class LinuxBackendTest(unittest.TestCase):
    def setUp(self):
        patcher = patch("livetrans.audio.linux._pactl",
                        side_effect=lambda *args: PACTL_SINKS if args[1] == "sinks"
                        else PACTL_INPUTS)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_parse_pactl_output(self):
        blocks = parse_blocks(PACTL_INPUTS)
        self.assertEqual([b["index"] for b in blocks], [101, 107, 110])
        self.assertEqual(blocks[0]["corked"], "yes")
        self.assertEqual(blocks[2]["properties"]["application.process.binary"], "mpv")

    def test_lists_sinks_and_playing_apps_first(self):
        backend = LinuxBackend()
        self.assertEqual([(d.id, d.label) for d in backend.list_devices()], [
            ("alsa_output.pci-0000_00_1f.3.analog-stereo", "Built-in Audio Analog Stereo"),
            ("bluez_output.AA_BB.1", "Headphones"),
        ])
        self.assertEqual([(a.name, a.active) for a in backend.list_apps()],
                         [("firefox", True), ("mpv", True)])

    def test_parec_arguments_follow_the_source(self):
        with patch("livetrans.audio.linux._command", side_effect=lambda name: name):
            system = ParecCapture(lambda chunk: None)
            self.assertIn("--device=@DEFAULT_MONITOR@", system._args(None))
            device = ParecCapture(lambda chunk: None, device="bluez_output.AA_BB.1")
            self.assertIn("--device=bluez_output.AA_BB.1.monitor", device._args(None))
            # Case and a Windows-style suffix do not matter; the playing, newest stream wins.
            app = ParecCapture(lambda chunk: None, app="Firefox.exe")
            self.assertEqual(app._pick_stream(), 107)
            self.assertIn("--monitor-stream=107", app._args(107))
            self.assertIn("--format=float32le", app._args(107))
            self.assertIsNone(ParecCapture(lambda chunk: None, app="vlc")._pick_stream())


if __name__ == "__main__":
    unittest.main()
