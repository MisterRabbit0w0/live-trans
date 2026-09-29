"""In-process and subprocess checks for the stdio JSON-RPC core server."""
from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import Mock

from livetrans.app.controller import AppController
from livetrans.app.loop import Loop
from livetrans.app.server import Server
from livetrans.config import AppConfig


class FakeRuntime:
    def __init__(self):
        self.on_event = lambda generation, event: None
        self.generation = 0
        self.stops = 0

    def start(self, cfg, paused=False, resume=False):
        self.generation += 1
        return self.generation

    def stop(self):
        self.generation += 1
        self.stops += 1
        return self.generation

    def pause(self, paused):
        pass

    def reconfigure(self, cfg):
        return self.generation

    def close(self):
        pass

    def send(self, kind, **kwargs):
        self.on_event(self.generation, dict(kind=kind, **kwargs))


class InProcessTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "config.json"
        self.loop = Loop()
        self.runtime = FakeRuntime()
        self.writer = io.StringIO()
        self._read_fd, self._write_fd = os.pipe()
        reader = os.fdopen(self._read_fd, "rb")

        def factory(on_change, on_event):
            return AppController(AppConfig(), self.path, self.runtime, loop=self.loop,
                                 on_change=on_change, on_event=on_event)

        self.server = Server(self.loop, factory, reader, self.writer)
        self.thread = threading.Thread(target=self.server.run, daemon=True)
        self.thread.start()

    def tearDown(self):
        if self._write_fd is not None:
            os.close(self._write_fd)
            self._write_fd = None
        self.thread.join(10)
        self.tmp.cleanup()

    def request(self, request_id, method, params=None):
        message = {"jsonrpc": "2.0", "id": request_id, "method": method}
        if params is not None:
            message["params"] = params
        os.write(self._write_fd, (json.dumps(message) + "\n").encode("utf-8"))

    def messages(self):
        return [json.loads(line) for line in self.writer.getvalue().splitlines() if line.strip()]

    def wait_for(self, predicate, timeout=5):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            messages = self.messages()
            if predicate(messages):
                return messages
            time.sleep(0.01)
        raise AssertionError(f"timed out; received {self.writer.getvalue()!r}")

    def test_snapshot_then_settings_set_pushes_one_state(self):
        self.request(1, "app.snapshot")
        messages = self.wait_for(lambda m: any(x.get("id") == 1 for x in m))
        [response] = [m for m in messages if m.get("id") == 1]
        self.assertEqual(response["result"]["state"]["app"]["state"], "idle")
        self.assertEqual(response["result"]["subtitles"], [])

        self.request(2, "settings.set", {"path": "ui.theme", "value": "dark"})
        messages = self.wait_for(lambda m: any(x.get("id") == 2 for x in m)
                                 and sum(x.get("method") == "state" for x in m) >= 1)
        states = [m for m in messages if m.get("method") == "state"]
        self.assertEqual(len(states), 1)
        self.assertTrue(states[0]["params"]["settings"]["dirty"])
        self.assertEqual(states[0]["params"]["settings"]["draft"]["ui"]["theme"], "dark")

    def test_protocol_errors(self):
        self.request(1, "bogus.method")
        os.write(self._write_fd, b"{not json\n")
        self.request(3, "app.adjustFont")  # missing required "delta" param
        # "delta" binds fine but breaks inside the handler: internal error, not bad params
        self.request(4, "app.adjustFont", {"delta": "bigger"})
        messages = self.wait_for(lambda m: sum("error" in x for x in m) == 4)
        errors = {m["id"]: m["error"]["code"] for m in messages if "error" in m}
        self.assertEqual(errors[1], -32601)
        self.assertEqual(errors[None], -32700)
        self.assertEqual(errors[3], -32602)
        self.assertEqual(errors[4], -32603)
        self.assertNotIn("bigger", json.dumps(errors))

    def test_runtime_events_push_subtitles(self):
        self.request(1, "app.start")
        self.wait_for(lambda m: any(x.get("id") == 1 for x in m))
        self.runtime.send("started", device="test", paused=False)
        self.runtime.send("entry", id=1, original="hello", language="en")
        self.runtime.send("translation", id=1, translation="你好")
        messages = self.wait_for(lambda m: any(
            x.get("method") == "subtitles"
            and x["params"]["entries"]
            and x["params"]["entries"][0].get("translation")
            for x in m))
        [note] = [m for m in messages if m.get("method") == "subtitles"]
        [entry] = note["params"]["entries"]
        self.assertEqual((entry["original"], entry["translation"]), ("hello", "你好"))

    def test_quit_flows(self):
        # A dirty draft asks for confirmation instead of stopping.
        self.request(1, "settings.set", {"path": "ui.theme", "value": "dark"})
        self.request(2, "app.requestQuit")
        messages = self.wait_for(lambda m: any(
            x.get("method") == "event"
            and x["params"]["name"] == "quitConfirmationRequested" for x in m))
        names = [x["params"]["name"] for x in messages if x.get("method") == "event"]
        self.assertIn("showRequested", names)
        self.assertEqual(self.runtime.stops, 0)

        # A clean draft quits once the runtime reports the session stopped.
        self.request(3, "app.discardSettings")
        self.request(4, "app.requestQuit")
        self.wait_for(lambda m: any(x.get("id") == 4 for x in m))
        self.assertEqual(self.runtime.stops, 1)
        self.runtime.send("stopped")
        self.wait_for(lambda m: any(
            x.get("method") == "event" and x["params"]["name"] == "quitReady" for x in m))
        self.thread.join(10)
        self.assertFalse(self.thread.is_alive())

    def test_stdin_eof_closes_controller(self):
        spy = Mock(wraps=self.server.controller.close)
        self.server.controller.close = spy
        os.close(self._write_fd)
        self._write_fd = None
        self.thread.join(10)
        self.assertFalse(self.thread.is_alive())
        spy.assert_called_once()


class SubprocessTests(unittest.TestCase):
    def test_preview_core_over_pipes(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            env = dict(os.environ)
            env.update({
                "HF_HUB_OFFLINE": "1",
                "APPDATA": str(tmp / "appdata"),
                "XDG_CONFIG_HOME": str(tmp / "xdg"),
                "HOME": str(tmp / "home"),
                "PYTHONIOENCODING": "utf-8",
            })
            proc = subprocess.Popen(
                [sys.executable, "-m", "livetrans.app", "--preview",
                 "--config", str(tmp / "config.json")],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                env=env, cwd=Path(__file__).resolve().parents[1])
            messages, stderr_lines = [], []
            lock = threading.Lock()

            def collect(stream, sink):
                for line in stream:
                    with lock:
                        sink.append(line)

            threads = [threading.Thread(target=collect, args=(proc.stdout, messages),
                                        daemon=True),
                       threading.Thread(target=collect, args=(proc.stderr, stderr_lines),
                                        daemon=True)]
            for thread in threads:
                thread.start()

            def send(request_id, method, params=None):
                message = {"jsonrpc": "2.0", "id": request_id, "method": method}
                if params is not None:
                    message["params"] = params
                proc.stdin.write((json.dumps(message) + "\n").encode("utf-8"))
                proc.stdin.flush()

            def parsed():
                with lock:
                    out = []
                    for line in messages:
                        out.append(json.loads(line))
                    return out

            def wait_for(predicate, timeout):
                deadline = time.monotonic() + timeout
                while time.monotonic() < deadline:
                    messages_now = parsed()
                    if predicate(messages_now):
                        return messages_now
                    time.sleep(0.02)
                stderr = b"".join(stderr_lines).decode("utf-8", "replace")
                raise AssertionError(f"timed out; stderr so far: {stderr}")

            try:
                send(1, "app.snapshot")
                messages_now = wait_for(lambda m: any(x.get("id") == 1 for x in m), 10)
                [response] = [m for m in messages_now if m.get("id") == 1]
                self.assertEqual(response["result"]["state"]["app"]["state"], "idle")

                send(2, "app.start")
                wait_for(lambda m: any(x.get("method") == "subtitles"
                                       and x["params"]["entries"] for x in m), 10)

                send(3, "app.shutdown")
                self.assertEqual(proc.wait(15), 0)
            finally:
                if proc.poll() is None:
                    proc.kill()
                    proc.wait(5)
                for stream in (proc.stdin, proc.stdout, proc.stderr):
                    stream.close()
            threads[0].join(5)
            with lock:
                raw_lines = list(messages)
            self.assertTrue(raw_lines)
            for line in raw_lines:
                self.assertIsInstance(json.loads(line), dict)


if __name__ == "__main__":
    unittest.main()
