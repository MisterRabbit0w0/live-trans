"""Collect the app's QML import closure, not every optional Qt module."""
import json
import subprocess
from pathlib import Path

from PyInstaller.utils.hooks.qt import add_qt6_dependencies, pyside6_library_info

hiddenimports, binaries, datas = add_qt6_dependencies(__file__)
info = pyside6_library_info
qml_path = info.location.get("QmlImportsPath") or info.location.get("Qml2ImportsPath")
if not qml_path:
    raise RuntimeError("PySide6 QML import directory is unavailable")
qml_root = Path(qml_path).resolve()
project = Path(__file__).resolve().parents[2]
scanner_candidates = [
    Path(info.package_location) / "qmlimportscanner.exe",
    Path(info.location.get("BinariesPath", "")) / "qmlimportscanner.exe",
]
scanner = next((path for path in scanner_candidates if path.is_file()), None)
if scanner is None:
    raise RuntimeError("PySide6 qmlimportscanner.exe is unavailable")
result = subprocess.run(
    [str(scanner), "-rootPath", str(project / "livetrans" / "ui" / "qml"),
     "-importPath", str(qml_root)],
    check=True, capture_output=True, text=True, encoding="utf-8",
)
imports = json.loads(result.stdout)
needed = {Path(item["path"]).resolve() for item in imports if item.get("path")}
missing = [item["name"] for item in imports
           if item.get("type") == "module" and not item.get("path")
           and item["name"] != "QML"]  # Built-in language types, registered by the engine.
if missing:
    raise RuntimeError(f"Unresolved QML imports: {missing}")
if not needed:
    raise RuntimeError("QML import scanner returned no modules")


def used_module(entry):
    parent = Path(entry[0]).resolve().parent
    while parent.is_relative_to(qml_root):
        if (parent / "qmldir").is_file():
            return parent in needed
        parent = parent.parent
    return False


qml_binaries, qml_datas = info.collect_qtqml_files()
binaries += [entry for entry in qml_binaries if used_module(entry)]
datas += [entry for entry in qml_datas if used_module(entry)]
