# Third-party software

LiveTrans is licensed under MIT. Binary distributions also include Python,
PySide6 / Qt, PyInstaller's bootloader, faster-whisper, CTranslate2, ONNX Runtime,
PyAudioWPatch / PortAudio, PyAV / FFmpeg and their dependencies. Their licenses
remain separate from LiveTrans's MIT license. Qt / PySide6 libraries used by
LiveTrans are used under LGPLv3. You may replace compatible shared libraries and
rebuild this application with modified libraries; reverse engineering for
debugging such modifications is permitted.

The `licenses/` directory in the binary distribution contains license and notice
files from the installed Python distributions, together with the upstream
LGPL / GPL texts and Silero VAD's MIT notice. `build-info.json` records the
exact package versions used to build the release. The portable ZIP and installer keep libraries as
separate files; use these distributions when replacing compatible Qt libraries.
The single EXE extracts its embedded files to a temporary directory at startup;
to use modified libraries, rebuild it with the supplied source and packaging
scripts, or use the portable package with replacement DLLs and QML plugins under
`_internal/PySide6/`. See `docs/releasing.md` for build instructions.

Corresponding upstream sources for the pinned Qt 6.11.1 build are available at
<https://download.qt.io/archive/qt/6.11/6.11.1/submodules/> (qtbase, qtdeclarative,
qtshadertools and qtsvg) and the PySide6 source at
<https://download.qt.io/official_releases/QtForPython/pyside6/PySide6-6.11.1-src/>.
PyAV's source and its FFmpeg build recipe are at
<https://github.com/PyAV-Org/PyAV/tree/v18.1.0>. No changes to these libraries are
made by the LiveTrans packaging scripts.

- Qt / PySide6: <https://www.qt.io/licensing/open-source-lgpl-obligations>
- Python: <https://docs.python.org/3/license.html>
- PyInstaller bootloader exception: <https://pyinstaller.org/en/stable/license.html>
- PyAV: <https://github.com/PyAV-Org/PyAV>; FFmpeg: <https://ffmpeg.org/legal.html>
- Silero VAD: <https://github.com/snakers4/silero-vad>, MIT license.

The bundled `livetrans/assets/silero_vad.onnx` is the VAD model. Whisper and
translation models are not included; their licenses apply when downloaded.
