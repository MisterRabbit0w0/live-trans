"""Build the Windows x64 CPU release: PyInstaller core, Tauri shell, NSIS + ZIP.

PyInstaller freezes ``livetrans-core`` (stdin JSON-RPC + model worker), the
onedir is staged under ``desktop/src-tauri/resources`` so the Tauri bundler
ships it next to the shell EXE, then ``tauri build`` produces the NSIS
installer and the same layout is zipped as the portable artifact. The build
never starts the frozen core or the shell; all release checks are static.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata as metadata
import importlib.util
import json
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path

import tomllib

ROOT = Path(__file__).resolve().parents[1]
DESKTOP = ROOT / "desktop"
SRC_TAURI = DESKTOP / "src-tauri"
# Tauri resources 的暂存目录（已加入 .gitignore，由本脚本每次重建）
RESOURCE_STAGE = SRC_TAURI / "resources"
TAURI_CLI = DESKTOP / "node_modules" / "@tauri-apps" / "cli" / "tauri.js"


def run(*args, cwd=ROOT):
    subprocess.run([str(arg) for arg in args], cwd=cwd, check=True)


def app_version():
    version = tomllib.loads((ROOT / "pyproject.toml").read_text("utf-8"))["project"]["version"]
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise SystemExit("Windows releases require a numeric X.Y.Z project version")
    return version


def prepare_metadata(version):
    spec = importlib.util.spec_from_file_location(
        "livetrans_icon", ROOT / "packaging" / "icon.py")
    icon = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(icon)

    generated = ROOT / "build" / "release-metadata"
    if generated.exists():
        shutil.rmtree(generated)
    generated.mkdir(parents=True, exist_ok=True)
    icon.write_icon(generated / "livetrans.ico")
    numbers = tuple(map(int, version.split("."))) + (0,)
    (generated / "version.txt").write_text(
        "VSVersionInfo(ffi=FixedFileInfo("
        f"filevers={numbers!r}, prodvers={numbers!r}, mask=0x3f, flags=0, "
        "OS=0x40004, fileType=1, subtype=0, date=(0,0)), kids=["
        "StringFileInfo([StringTable('040904B0', ["
        "StringStruct('CompanyName', 'MisterRabbit0w0'),"
        "StringStruct('FileDescription', 'LiveTrans'),"
        f"StringStruct('FileVersion', '{version}'),"
        "StringStruct('ProductName', 'LiveTrans'),"
        f"StringStruct('ProductVersion', '{version}'),"
        "StringStruct('LegalCopyright', 'Copyright 2026 MisterRabbit0w0')"
        "])]), VarFileInfo([VarStruct('Translation', [1033, 1200])])])", encoding="utf-8",
    )
    versions = {}
    licenses = generated / "licenses"
    shutil.copytree(ROOT / "packaging" / "licenses", licenses / "upstream", dirs_exist_ok=True)
    shutil.copyfile(ROOT / "THIRD_PARTY_NOTICES.md", licenses / "THIRD_PARTY_NOTICES.md")
    for dist in metadata.distributions():
        name = dist.metadata["Name"]
        versions[name] = dist.version
        for file in dist.files or ():
            if (any(part.lower().startswith(("license", "copying", "notice"))
                    for part in file.parts) and Path(dist.locate_file(file)).is_file()):
                # Keep package-relative names; never copy direct_url.json or environment paths.
                target = licenses / name / str(file).replace("../", "")
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(dist.locate_file(file), target)
    python_license = Path(sys.base_prefix) / "LICENSE.txt"
    if not python_license.is_file():
        raise SystemExit("Python's LICENSE.txt is missing from the build interpreter")
    shutil.copyfile(python_license, licenses / "Python-LICENSE.txt")
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT).decode().strip()
    (generated / "build-info.json").write_text(json.dumps({
        "version": version, "commit": revision, "profile": "windows-x64-cpu",
        "dirty": bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT)),
        "python": platform.python_version(), "packages": dict(sorted(versions.items())),
    }, indent=2) + "\n", encoding="utf-8")
    return generated


def freeze_core():
    """PyInstaller → build/frozen/livetrans-core/，随后立即做静态资源检查。"""
    run(sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
        "--distpath", ROOT / "build" / "frozen", "--workpath", ROOT / "build" / "pyinstaller",
        ROOT / "packaging" / "livetrans.spec")
    frozen = ROOT / "build" / "frozen"
    run(sys.executable, ROOT / "scripts" / "check_windows_package.py", frozen)
    return frozen / "livetrans-core"


def stage_core_resource(core_dir: Path) -> Path:
    """把 onedir 核心映射到 Tauri 资源目录，安装/便携布局保持一致。"""
    target = RESOURCE_STAGE / "livetrans-core"
    if not target.is_dir():
        raise SystemExit(f"Tauri 资源目录缺失（应含占位 .gitkeep）: {target}")
    for child in target.iterdir():
        if child.name == ".gitkeep":  # 占位文件留在 git 中，不清除
            continue
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()
    shutil.copytree(core_dir, target, dirs_exist_ok=True)
    return target


def build_shell(skip_installer: bool) -> Path:
    """tauri build：release 壳 EXE；默认连带 NSIS 安装包。"""
    if not TAURI_CLI.is_file():
        raise SystemExit("desktop/node_modules 缺失，先在 desktop/ 运行 npm ci")
    node = shutil.which("node")
    if not node:
        raise SystemExit("找不到 node，请先安装 Node.js")
    bundles = ["--no-bundle"] if skip_installer else ["--bundles", "nsis"]
    run(node, TAURI_CLI, "build", *bundles, cwd=DESKTOP)
    shell = SRC_TAURI / "target" / "release" / "livetrans.exe"
    if not shell.is_file():
        raise SystemExit(f"Tauri 未产出壳可执行文件: {shell}")
    return shell


def collect_nsis(artifacts: Path, stem: str) -> Path:
    nsis_dir = SRC_TAURI / "target" / "release" / "bundle" / "nsis"
    installers = sorted(nsis_dir.glob("*-setup.exe")) if nsis_dir.is_dir() else []
    if not installers:
        raise SystemExit(f"NSIS 安装包缺失: {nsis_dir}")
    if len(installers) > 1:
        raise SystemExit(f"NSIS 安装包不唯一: {[p.name for p in installers]}")
    target = artifacts / f"{stem}-setup.exe"
    shutil.copyfile(installers[0], target)
    return target


def stage_portable(core_dir: Path, shell: Path, generated: Path, stem: str) -> Path:
    """便携 ZIP 与安装版同布局：livetrans.exe 旁挂 livetrans-core/。"""
    stage = ROOT / "build" / "portable" / stem
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir(parents=True)
    shutil.copyfile(shell, stage / "livetrans.exe")
    shutil.copytree(core_dir, stage / "livetrans-core")
    shutil.copytree(generated / "licenses", stage / "licenses")
    shutil.copyfile(generated / "build-info.json", stage / "build-info.json")
    # 布局终检 + 壳二进制构建机路径扫描（静态，不启动进程）
    run(sys.executable, ROOT / "scripts" / "check_release_layout.py", stage)
    return stage


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-installer", action="store_true",
                        help="跳过 NSIS 打包（--no-bundle），仍产出便携 ZIP")
    args = parser.parse_args()
    if sys.platform != "win32" or platform.machine().lower() not in {"amd64", "x86_64"}:
        raise SystemExit("Run this build with Windows x64 Python")
    version = app_version()
    generated = prepare_metadata(version)
    artifacts = ROOT / "dist" / "windows"
    # Refuse stale output, rather than deleting a user-supplied directory.
    if artifacts.exists() and any(artifacts.iterdir()):
        raise SystemExit("dist/windows is not empty; move the previous release before rebuilding")
    artifacts.mkdir(parents=True, exist_ok=True)
    core_dir = freeze_core()
    stage_core_resource(core_dir)
    shell = build_shell(args.skip_installer)
    stem = f"LiveTrans-{version}-windows-x64"
    if not args.skip_installer:
        collect_nsis(artifacts, stem)
    stage = stage_portable(core_dir, shell, generated, stem)
    shutil.make_archive(str(artifacts / f"{stem}-portable"), "zip",
                        stage.parent, stage.name)
    shutil.copyfile(generated / "build-info.json", artifacts / "build-info.json")
    shutil.make_archive(str(artifacts / "third-party-licenses"), "zip", generated, "licenses")
    checksums = []
    for file in sorted(artifacts.iterdir()):
        with file.open("rb") as stream:
            checksums.append(f"{hashlib.file_digest(stream, 'sha256').hexdigest()}  {file.name}")
    (artifacts / "SHA256SUMS.txt").write_text("\n".join(checksums) + "\n", encoding="utf-8")
    print(f"Windows release artifacts: {artifacts}")


if __name__ == "__main__":
    main()
