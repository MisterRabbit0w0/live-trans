# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, copy_metadata

root = Path(SPECPATH).parent
generated = root / "build" / "release-metadata"
datas = collect_data_files("livetrans")
datas += [(str(root / "LICENSE"), "."), (str(root / "THIRD_PARTY_NOTICES.md"), ".")]
datas += [(str(generated / "licenses"), "licenses")]
datas += [(str(generated / "build-info.json"), ".")]
for distribution in ("faster-whisper", "ctranslate2", "huggingface-hub", "tokenizers"):
    datas += copy_metadata(distribution)

analysis = Analysis(
    [str(root / "packaging" / "entrypoint.py")],
    pathex=[str(root)],
    binaries=collect_dynamic_libs("ctranslate2"),
    datas=datas,
    hiddenimports=["PySide6.QtSvg", "PySide6.QtQuick", "PySide6.QtQuickControls2"],
    hookspath=[str(root / "packaging" / "hooks")],
    # CPU distribution. QtQml's official hook collects QML modules and plugins.
    excludes=["torch", "tensorflow", "matplotlib", "IPython", "PyQt5", "PyQt6",
              "PySide2", "nvidia"],
    noarchive=False,
    optimize=1,
)
pyz = PYZ(analysis.pure)
options = dict(
    debug=False,
    strip=False,
    upx=False,
    console=False,
    icon=str(generated / "livetrans.ico"),
    version=str(generated / "version.txt"),
    contents_directory="_internal",
)
portable = EXE(pyz, analysis.scripts, [], exclude_binaries=True, name="LiveTrans", **options)
COLLECT(portable, analysis.binaries, analysis.datas, strip=False, upx=False, name="LiveTrans")
EXE(pyz, analysis.scripts, analysis.binaries, analysis.datas,
    name="LiveTrans-standalone", **options)
