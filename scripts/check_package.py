"""Verify that wheel and sdist include QML, the application icon and VAD model."""
from __future__ import annotations

import argparse
import tarfile
import zipfile
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, help="artifact directory (default: dist)")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    required = {p.relative_to(root).as_posix()
                for p in (root / "livetrans/ui/qml").iterdir() if p.is_file()}
    required.add("livetrans/assets/silero_vad.onnx")
    required.add("livetrans/assets/livetrans.svg")
    directory = args.directory or root / "dist"
    artifacts = sorted(directory.glob("*.whl"))
    sources = sorted(directory.glob("*.tar.gz"))
    if not artifacts or not sources:
        raise SystemExit("Build both wheel and sdist first: python -m build")
    for path in artifacts + sources:
        if path.suffix == ".whl":
            with zipfile.ZipFile(path) as archive:
                entries = set(archive.namelist())
        else:
            with tarfile.open(path) as archive:
                entries = {member.name.partition("/")[2] for member in archive.getmembers()}
        missing = required - entries
        if path.suffix != ".whl":
            build_files = {"packaging/livetrans.spec", "packaging/windows.iss",
                           "packaging/requirements-windows.lock", "packaging/entrypoint.py",
                           "packaging/hooks/hook-PySide6.QtQml.py", "scripts/build_windows.py",
                           "scripts/check_windows_package.py", "scripts/release_artifacts.py",
                           "CONTRIBUTING.md", "SECURITY.md", "THIRD_PARTY_NOTICES.md"}
            missing |= build_files - entries
        for notice in ("THIRD_PARTY_NOTICES.md", "Silero-VAD-MIT.txt", "LGPL-3.0-only.txt"):
            if not any(Path(entry).name == notice for entry in entries):
                missing.add(notice)
        if missing:
            raise SystemExit(f"{path.name}: missing {sorted(missing)}")
        print(f"{path.name}: all {len(required)} UI / model resources present")


if __name__ == "__main__":
    main()
