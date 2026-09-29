"""Inspect frozen payloads without launching either executable."""
from __future__ import annotations

import argparse
from pathlib import Path

from PyInstaller.archive.readers import CArchiveReader

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    directory = args.directory.resolve()
    folder = directory / "LiveTrans"
    internal = folder / "_internal"
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
    onefile = CArchiveReader(str(directory / "LiveTrans-standalone.exe"))
    def normalize(name):
        normalized = name.replace("\\", "/")
        if normalized.startswith("_internal/"):
            normalized = normalized[len("_internal/"):]
        return normalized

    embedded = {normalize(name) for name in onefile.toc}
    for label, names in (("portable", entries), ("standalone", embedded)):
        missing = required - names
        if not any(name.startswith("licenses/") for name in names):
            missing.add("licenses/")
        if missing:
            raise SystemExit(f"{label}: missing {sorted(missing)}")
        if any(Path(name).name in {"config.json", ".env", "direct_url.json"} for name in names):
            raise SystemExit(f"{label}: private configuration or build paths included")
        print(f"{label}: icon, VAD, native plugin and notices present")
    if not (folder / "LiveTrans.exe").is_file():
        raise SystemExit("Missing portable LiveTrans.exe")


if __name__ == "__main__":
    main()
