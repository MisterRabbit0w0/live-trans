"""发行布局与壳二进制的静态检查，不启动任何进程。

核对壳 EXE 旁挂 ``livetrans-core/``（onedir），并扫描壳 EXE 中的构建机路径残留。

用法::

    python scripts/check_release_layout.py build\\portable\\LiveTrans-X.Y.Z-windows-x64
"""
from __future__ import annotations

import argparse
from pathlib import Path

# release 壳二进制不得内嵌开发机解释器与仓库路径的编译期引用
FORBIDDEN_STRINGS = (b".venv", b"CARGO_MANIFEST_DIR", b"LIVETRANS_CORE_PYTHON")


def check_layout(layout: Path) -> list[str]:
    errors = []
    for relative in ("livetrans.exe", "livetrans-core/livetrans-core.exe"):
        if not (layout / relative).is_file():
            errors.append(f"缺 {relative}")
    if not (layout / "livetrans-core" / "_internal").is_dir():
        errors.append("缺 livetrans-core/_internal")
    return errors


def check_shell_binary(shell_exe: Path) -> list[str]:
    if not shell_exe.is_file():
        return []  # 缺失已由布局检查报告
    data = shell_exe.read_bytes()
    found = [needle.decode() for needle in FORBIDDEN_STRINGS if needle in data]
    return [f"{shell_exe.name} 残留开发路径引用: {found}"] if found else []


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("layout", type=Path, help="发行布局目录（livetrans.exe + livetrans-core/）")
    layout = parser.parse_args().layout.resolve()
    errors = check_layout(layout) + check_shell_binary(layout / "livetrans.exe")
    if errors:
        raise SystemExit(f"发行布局检查失败（{layout}）: " + "; ".join(errors))
    print(f"release layout: {layout} 布局正确，壳无构建机路径残留")


if __name__ == "__main__":
    main()
