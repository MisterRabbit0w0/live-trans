"""校验 Tauri Rust crate 与 npm 包的 major.minor 一致。

`tauri build` 在两者 major/minor 不一致时直接报错，但 CI 的前端与 Rust
检查不跑 `tauri build`，依赖更新单独升级一侧时只有发行构建才会暴露。
本脚本读取锁文件中的实际解析版本，在 CI 中提前拦截。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import tomllib

ROOT = Path(__file__).resolve().parents[1]
CARGO_LOCK = ROOT / "desktop" / "src-tauri" / "Cargo.lock"
PACKAGE_LOCK = ROOT / "desktop" / "package-lock.json"
# npm 包 ↔ 对应的 Rust crate
PAIRS = {"@tauri-apps/api": "tauri", "@tauri-apps/cli": "tauri"}


def _major_minor(version: str) -> tuple[str, str]:
    major, minor, *_ = version.split(".")
    return major, minor


def main() -> int:
    crates = {}
    for package in tomllib.loads(CARGO_LOCK.read_text("utf-8")).get("package", []):
        crates.setdefault(package["name"], set()).add(package["version"])
    packages = json.loads(PACKAGE_LOCK.read_text("utf-8"))["packages"]
    errors = []
    for npm_name, crate in PAIRS.items():
        npm_version = packages.get(f"node_modules/{npm_name}", {}).get("version")
        crate_versions = crates.get(crate, set())
        if not npm_version or len(crate_versions) != 1:
            errors.append(f"无法确定 {npm_name} / {crate} 的唯一版本")
            continue
        (crate_version,) = crate_versions
        if _major_minor(npm_version) != _major_minor(crate_version):
            errors.append(f"{npm_name} {npm_version} 与 {crate} {crate_version} major.minor 不一致")
    if errors:
        print("Tauri 版本检查失败: " + "; ".join(errors), file=sys.stderr)
        return 1
    print("Tauri 版本一致：npm 包与 Rust crate major.minor 相同")
    return 0


if __name__ == "__main__":
    sys.exit(main())
