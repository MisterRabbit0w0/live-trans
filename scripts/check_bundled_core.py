"""tauri build 前置检查：随包冻结核心必须已就位。

由 tauri.conf.json 的 beforeBundleCommand 调用。PyInstaller onedir 由
scripts/build_windows.py 复制到 desktop/src-tauri/resources/livetrans-core；
直接手工 tauri build 而没有冻结核心时给出明确指引，而不是产出缺核心的
安装包。
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "desktop" / "src-tauri" / "resources" / "livetrans-core" / "livetrans-core.exe"


def main():
    if not CORE.is_file():
        raise SystemExit(
            "缺少随包冻结核心 livetrans-core.exe，请先运行 "
            "python scripts/build_windows.py（或先 PyInstaller 再 tauri build）")
    print(f"bundled core ready: {CORE}")


if __name__ == "__main__":
    main()
