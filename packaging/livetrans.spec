# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, copy_metadata

root = Path(SPECPATH).parent
generated = root / "build" / "release-metadata"
datas = collect_data_files("livetrans")
datas += [(str(root / "LICENSE"), "."), (str(root / "THIRD_PARTY_NOTICES.md"), ".")]
datas += [(str(generated / "licenses"), "licenses")]
datas += [(str(generated / "build-info.json"), ".")]
# Plain worker sources let an external Python runtime run the model process.
datas += [(str(root / "livetrans" / "__init__.py"), "runtime-src/livetrans")]
datas += [(str(root / "livetrans" / "worker" / name), "runtime-src/livetrans/worker")
          for name in ("__init__.py", "__main__.py", "protocol.py", "server.py", "engine.py",
                       "models.py")]
for distribution in ("faster-whisper", "ctranslate2", "huggingface-hub", "tokenizers"):
    datas += copy_metadata(distribution)

analysis = Analysis(
    [str(root / "packaging" / "entrypoint.py")],
    pathex=[str(root)],
    binaries=collect_dynamic_libs("ctranslate2"),
    datas=datas,
    hiddenimports=["livetrans.worker.server", "livetrans.worker.engine",
                   "livetrans.audio.windows.loopback", "livetrans.audio.windows.process_loopback"],
    hookspath=[],
    # CPU distribution without legacy UI frameworks.
    excludes=["torch", "tensorflow", "matplotlib", "IPython", "PyQt5", "PyQt6",
              "PySide2", "PySide6", "nvidia", "livetrans.audio.linux", "livetrans.audio.macos"],
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
