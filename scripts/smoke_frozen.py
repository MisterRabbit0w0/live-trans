"""冻结版 livetrans-core 的管道烟测。

不启动音频、不加载模型、不访问网络：向 ``livetrans-core.exe --preview``
写入 app.snapshot / app.start / app.shutdown 请求并断言响应、通知与退出码；
再以 ``--livetrans-worker`` 启动同一可执行文件，断言握手帧。可选地核对
发行布局（壳 EXE 旁挂 livetrans-core/）并扫描壳 EXE 中的构建机路径残留。

用法::

    python scripts/smoke_frozen.py build/frozen/livetrans-core
    python scripts/smoke_frozen.py ... --layout dist\\windows\\stage-portable
    python scripts/smoke_frozen.py ... --shell-exe dist\\windows\\stage-portable\\livetrans.exe
"""
from __future__ import annotations

import argparse
import json
import os
import struct
import subprocess
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAX_HEADER = 1 << 20
LENGTH = struct.Struct(">I")
# release 壳二进制不得内嵌开发机解释器与仓库路径的编译期引用
FORBIDDEN_STRINGS = (b".venv", b"CARGO_MANIFEST_DIR", b"LIVETRANS_CORE_PYTHON")


class SmokeFailure(AssertionError):
    """烟测断言失败，退出码 1。"""


def _require(condition, message):
    if not condition:
        raise SmokeFailure(message)


def _resolve_core(path: Path) -> Path:
    if path.is_dir():
        if (path / "livetrans-core.exe").is_file():
            path = path / "livetrans-core.exe"
        elif (path / "livetrans-core" / "livetrans-core.exe").is_file():
            path = path / "livetrans-core" / "livetrans-core.exe"
    _require(path.is_file(), f"找不到冻结核心可执行文件: {path}")
    return path.resolve()


def check_core(core: Path, timeout_s: float) -> None:
    """snapshot → start → shutdown：断言响应、subtitles 通知与退出码 0。"""
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
            [str(core), "--preview", "--config", str(tmp / "config.json")],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env=env, cwd=core.parent)
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
                return [json.loads(line) for line in messages]

        def wait_for(predicate, limit):
            deadline = time.monotonic() + limit
            while time.monotonic() < deadline:
                current = parsed()
                if predicate(current):
                    return current
                if proc.poll() is not None:
                    break
                time.sleep(0.02)
            stderr = b"".join(stderr_lines).decode("utf-8", "replace")
            raise SmokeFailure(f"等待核心消息超时；stderr: {stderr[-2000:]}")

        try:
            send(1, "app.snapshot")
            current = wait_for(lambda m: any(x.get("id") == 1 for x in m), timeout_s)
            [response] = [m for m in current if m.get("id") == 1]
            _require("result" in response, f"app.snapshot 未返回 result: {response}")
            _require(response["result"]["state"]["app"]["state"] == "idle",
                     f"app.snapshot 状态异常: {response['result']}")

            send(2, "app.start")
            wait_for(lambda m: any(x.get("method") == "subtitles"
                                   and x["params"]["entries"] for x in m), timeout_s)

            send(3, "app.shutdown")
            code = proc.wait(timeout_s)
            _require(code == 0, f"app.shutdown 后退出码为 {code}")
        except subprocess.TimeoutExpired as error:
            proc.kill()
            raise SmokeFailure("app.shutdown 后进程未退出") from error
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait(5)
            for stream in (proc.stdin, proc.stdout, proc.stderr):
                stream.close()
        threads[0].join(5)
        with lock:
            raw_lines = list(messages)
        _require(raw_lines, "核心未输出任何协议行")
        for line in raw_lines:
            _require(isinstance(json.loads(line), dict),
                     f"核心协议行不是 JSON 对象: {line[:200]!r}")
    print("core: snapshot/start/shutdown 与 subtitles 通知通过")


def _read_exact(stream, size):
    chunks, remaining = [], size
    while remaining:
        chunk = stream.read(remaining)
        if not chunk:
            raise SmokeFailure("worker 输出流提前关闭")
    return b"".join(chunks)


def check_worker(core: Path, timeout_s: float) -> None:
    """``--livetrans-worker`` 首帧必须是 hello。"""
    proc = subprocess.Popen([str(core), "--livetrans-worker"],
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, cwd=core.parent)
    result = {}

    def read_hello():
        try:
            (size,) = LENGTH.unpack(_read_exact(proc.stdout, LENGTH.size))
            if size > MAX_HEADER:
                raise SmokeFailure(f"worker hello 头过大: {size}")
            header = json.loads(_read_exact(proc.stdout, size).decode("utf-8"))
            (payload_size,) = LENGTH.unpack(_read_exact(proc.stdout, LENGTH.size))
            if payload_size:
                _read_exact(proc.stdout, payload_size)
            result["header"] = header
        except Exception as error:  # 读超时以外的原因同样要回传
            result["error"] = error

    try:
        reader = threading.Thread(target=read_hello, daemon=True)
        reader.start()
        reader.join(timeout_s)
        if reader.is_alive():
            stderr = proc.stderr.read() if proc.poll() is not None else "<进程仍在运行>".encode()
            raise SmokeFailure(
                f"等待 worker hello 帧超时；stderr: {stderr[-2000:].decode('utf-8', 'replace')}")
        if "error" in result:
            raise result["error"]
        header = result.get("header")
        _require(isinstance(header, dict) and header.get("type") == "hello",
                 f"worker 首帧不是 hello: {header}")
        _require(isinstance(header.get("version"), int), f"hello 缺 version: {header}")
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(5)
        for stream in (proc.stdin, proc.stdout, proc.stderr):
            stream.close()
    # EOF（应用退出）应让 worker 正常结束
    code = proc.wait(timeout_s)
    _require(code == 0, f"worker 关闭 stdin 后退出码为 {code}")
    print("worker: --livetrans-worker hello 帧与 EOF 退出通过")


def check_layout(layout: Path, core: Path) -> None:
    """发行布局：壳 EXE 旁必须带 livetrans-core/livetrans-core.exe。"""
    layout = layout.resolve()
    _require((layout / "livetrans.exe").is_file(), f"布局缺 livetrans.exe: {layout}")
    _require((layout / "livetrans-core" / "livetrans-core.exe").is_file(),
             f"布局缺 livetrans-core/livetrans-core.exe: {layout}")
    _require((layout / "livetrans-core" / "_internal").is_dir(),
             f"布局缺 livetrans-core/_internal: {layout}")
    _require(core.parent.parent.samefile(layout),
             f"布局核心与待测核心不一致: {core} vs {layout}")
    print(f"layout: {layout} 下壳与核心相对布局正确")


def check_shell_binary(shell_exe: Path) -> None:
    """release 壳不得残留构建机路径回退的编译期字符串。"""
    _require(shell_exe.is_file(), f"壳 EXE 不存在: {shell_exe}")
    data = shell_exe.read_bytes()
    found = [needle.decode("utf-8") for needle in FORBIDDEN_STRINGS if needle in data]
    _require(not found, f"{shell_exe.name} 残留开发路径引用: {found}")
    print(f"shell: {shell_exe.name} 无构建机路径残留")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("core", type=Path,
                        help="livetrans-core.exe、其所在 onedir 或 build/frozen 目录")
    parser.add_argument("--layout", type=Path,
                        help="发行布局目录（livetrans.exe + livetrans-core/）")
    parser.add_argument("--shell-exe", type=Path,
                        help="release 壳 EXE；扫描构建机路径残留")
    parser.add_argument("--timeout", type=float, default=120.0,
                        help="单次协议等待秒数（默认 120；CI 冷机冻结引导较慢）")
    args = parser.parse_args()
    core = _resolve_core(args.core)
    try:
        check_core(core, args.timeout)
        check_worker(core, args.timeout)
        if args.layout:
            check_layout(args.layout, core)
        if args.shell_exe:
            check_shell_binary(args.shell_exe)
    except (SmokeFailure, OSError, json.JSONDecodeError) as error:
        raise SystemExit(f"烟测失败: {error}") from error
    print("smoke_frozen: 全部检查通过")


if __name__ == "__main__":
    main()
