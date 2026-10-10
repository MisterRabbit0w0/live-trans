"""Inspect the frozen livetrans-core payload without launching it."""
from __future__ import annotations

import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    directory = args.directory.resolve()
    # PyInstaller onedir：外壳经 Tauri resources 按相同相对布局安装/便携分发。
    folder = directory / "livetrans-core"
    internal = folder / "_internal"
    if not (folder / "livetrans-core.exe").is_file():
        raise SystemExit("Missing livetrans-core/livetrans-core.exe")
    if not internal.is_dir():
        raise SystemExit("Missing livetrans-core/_internal directory")
    required = {"livetrans/assets/silero_vad.onnx", "livetrans/assets/livetrans.svg",
                "LICENSE", "THIRD_PARTY_NOTICES.md", "build-info.json",
                "licenses/upstream/LGPL-3.0-only.txt", "licenses/upstream/GPL-3.0-only.txt",
                "licenses/upstream/Silero-VAD-MIT.txt", "licenses/Python-LICENSE.txt",
                "runtime-src/livetrans/__init__.py"}
    required |= {f"runtime-src/livetrans/worker/{name}"
                 for name in ("__init__.py", "__main__.py", "protocol.py", "server.py",
                              "engine.py", "models.py")}
    entries = {path.relative_to(internal).as_posix() for path in internal.rglob("*")
               if path.is_file()}
    missing = required - entries
    if not any(name.startswith("licenses/") for name in entries):
        missing.add("licenses/")
    if missing:
        raise SystemExit(f"livetrans-core: missing {sorted(missing)}")
    if any(Path(name).name in {"config.json", ".env", "direct_url.json"}
           for name in entries):
        raise SystemExit("livetrans-core: private configuration or build paths included")
    print("livetrans-core: icon, VAD, worker sources and notices present")


if __name__ == "__main__":
    main()
