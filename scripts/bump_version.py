"""项目版本单一来源同步工具。

以 pyproject.toml [project].version 为唯一来源，同步其余清单中的版本号：
  - pyproject.toml          （来源，仅校验，不修改）
  - desktop/package.json
  - desktop/src-tauri/tauri.conf.json
  - desktop/src-tauri/Cargo.toml  ([package] 段）

用法：
  python scripts/bump_version.py X.Y.Z     写入全部清单
  python scripts/bump_version.py --check   校验一致，不一致以非零退出并列出漂移
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import tomllib

REPO_ROOT = Path(__file__).resolve().parent.parent

_PYPROJECT = REPO_ROOT / "pyproject.toml"
_PACKAGE_JSON = REPO_ROOT / "desktop" / "package.json"
_TAURI_CONF = REPO_ROOT / "desktop" / "src-tauri" / "tauri.conf.json"
_CARGO_TOML = REPO_ROOT / "desktop" / "src-tauri" / "Cargo.toml"

# 语义化版本：X.Y.Z，允许预发布/构建后缀（与 release-please 输出一致）
_VERSION_RE = re.compile(
    r"^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$"
)


def _source_version() -> str:
    with _PYPROJECT.open("rb") as fh:
        return tomllib.load(fh)["project"]["version"]


def _read_json_version(path: Path) -> str:
    data = json.loads(path.read_text(encoding="utf-8"))
    return str(data["version"])


def _write_json_version(path: Path, version: str) -> bool:
    text = path.read_text(encoding="utf-8")
    new_text, count = re.subn(
        r'("version"\s*:\s*")[^"]*(")',
        rf"\g<1>{version}\g<2>",
        text,
        count=1,
    )
    if count != 1:
        raise RuntimeError(f"{path}: 未找到顶层 version 字段")
    if new_text == text:
        return False
    path.write_text(new_text, encoding="utf-8")
    return True


def _read_cargo_version() -> str:
    with _CARGO_TOML.open("rb") as fh:
        return tomllib.load(fh)["package"]["version"]


def _write_cargo_version(version: str) -> bool:
    text = _CARGO_TOML.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    in_package = False
    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("["):
            in_package = stripped == "[package]"
            continue
        if in_package and stripped.startswith("version"):
            match = re.match(r'^(\s*version\s*=\s*")[^"]*("[^\n]*)$', line.rstrip("\n"))
            if match is None:
                raise RuntimeError(f"{_CARGO_TOML}: 无法解析 [package] version 行")
            new_line = f"{match.group(1)}{version}{match.group(2)}\n"
            if new_line == line:
                return False
            lines[index] = new_line
            _CARGO_TOML.write_text("".join(lines), encoding="utf-8")
            return True


def _versions() -> dict[str, str]:
    return {
        str(_PYPROJECT.relative_to(REPO_ROOT)): _source_version(),
        str(_PACKAGE_JSON.relative_to(REPO_ROOT)): _read_json_version(_PACKAGE_JSON),
        str(_TAURI_CONF.relative_to(REPO_ROOT)): _read_json_version(_TAURI_CONF),
        str(_CARGO_TOML.relative_to(REPO_ROOT)): _read_cargo_version(),
    }


def _check() -> int:
    source = _source_version()
    drift = []
    for name, version in _versions().items():
        if version != source:
            drift.append(f"  {name}: {version}（来源 {source}）")
    if drift:
        print("版本不一致，与 pyproject.toml 漂移：")
        print("\n".join(drift))
        return 1
    print(f"版本一致：{source}")
    return 0


def _bump(version: str) -> int:
    source = _source_version()
    if version != source:
        print(
            f"错误：pyproject.toml 当前为 {source}，请先更新来源再同步。",
            file=sys.stderr,
        )
        return 1
    changed = []
    for path, writer in (
        (_PACKAGE_JSON, lambda: _write_json_version(_PACKAGE_JSON, version)),
        (_TAURI_CONF, lambda: _write_json_version(_TAURI_CONF, version)),
        (_CARGO_TOML, lambda: _write_cargo_version(version)),
    ):
        if writer():
            changed.append(str(path.relative_to(REPO_ROOT)))
    if changed:
        print(f"已写入 {version}：" + "、".join(changed))
    else:
        print(f"版本已为 {version}，无需修改。")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args == ["--check"]:
        return _check()
    if len(args) == 1 and _VERSION_RE.match(args[0]):
        return _bump(args[0])
    print(
        f"用法：{Path(sys.argv[0]).name} X.Y.Z | --check",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
