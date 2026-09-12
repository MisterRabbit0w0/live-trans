"""Build Windows x64 CPU binaries without starting the application."""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata as metadata
import io
import json
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path

import tomllib

ROOT = Path(__file__).resolve().parents[1]


def run(*args):
    subprocess.run([str(arg) for arg in args], cwd=ROOT, check=True)


def app_version():
    version = tomllib.loads((ROOT / "pyproject.toml").read_text("utf-8"))["project"]["version"]
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise SystemExit("Windows releases require a numeric X.Y.Z project version")
    return version


def prepare_metadata(version):
    from PIL import Image
    from PySide6.QtCore import QBuffer, QIODevice, Qt
    from PySide6.QtGui import QImage, QPainter
    from PySide6.QtSvg import QSvgRenderer

    generated = ROOT / "build" / "release-metadata"
    generated.mkdir(parents=True, exist_ok=True)
    renderer = QSvgRenderer(str(ROOT / "livetrans" / "assets" / "livetrans.svg"))
    if not renderer.isValid():
        raise SystemExit("Invalid application SVG")
    image = QImage(256, 256, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    renderer.render(painter)
    painter.end()
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buffer, "PNG")
    Image.open(io.BytesIO(bytes(buffer.data()))).save(
        generated / "livetrans.ico", sizes=[(n, n) for n in (16, 24, 32, 48, 64, 128, 256)],
    )
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iscc", type=Path, help="Inno Setup compiler; required for installer")
    parser.add_argument("--skip-installer", action="store_true", help="only build ZIP and EXE")
    args = parser.parse_args()
    if sys.platform != "win32" or platform.machine().lower() not in {"amd64", "x86_64"}:
        raise SystemExit("Run this build with Windows x64 Python")
    if not args.skip_installer and (not args.iscc or not args.iscc.is_file()):
        raise SystemExit("Pass --iscc PATH/ISCC.exe, or --skip-installer for binaries only")
    version = app_version()
    generated = prepare_metadata(version)
    artifacts = ROOT / "dist" / "windows"
    # Refuse stale output, rather than deleting a user-supplied directory.
    if artifacts.exists() and any(artifacts.iterdir()):
        raise SystemExit("dist/windows is not empty; move the previous release before rebuilding")
    artifacts.mkdir(parents=True, exist_ok=True)
    run(sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
        "--distpath", ROOT / "build" / "frozen", "--workpath", ROOT / "build" / "pyinstaller",
        ROOT / "packaging" / "livetrans.spec")
    frozen = ROOT / "build" / "frozen"
    run(sys.executable, ROOT / "scripts" / "check_windows_package.py", frozen)
    stem = f"LiveTrans-{version}-windows-x64"
    shutil.make_archive(str(artifacts / f"{stem}-portable"), "zip", frozen, "LiveTrans")
    shutil.copyfile(frozen / "LiveTrans-standalone.exe", artifacts / f"{stem}-standalone.exe")
    if not args.skip_installer:
        run(args.iscc.resolve(), f"/DAppVersion={version}", f"/DSourceDir={frozen / 'LiveTrans'}",
            f"/DOutputDir={artifacts}", f"/DAppIcon={generated / 'livetrans.ico'}",
            ROOT / "packaging" / "windows.iss")
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
