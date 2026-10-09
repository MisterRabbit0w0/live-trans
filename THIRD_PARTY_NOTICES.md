# Third-party software

LiveTrans is licensed under MIT. Binary distributions also include Python,
PyInstaller's bootloader, faster-whisper, CTranslate2, ONNX Runtime,
PyAudioWPatch / PortAudio, PyAV / FFmpeg and their dependencies. Their licenses
remain separate from LiveTrans's MIT license.

PySide6 / Qt is used only at build time to render the application icon
(`packaging/icon.py`); it is not shipped in binary distributions.

The `licenses/` directory in the binary distribution contains license and notice
files from the installed Python distributions, together with the upstream
LGPL / GPL texts required by bundled components and Silero VAD's MIT notice.
`build-info.json` records the exact package versions used to build the release.
The portable ZIP and installer keep libraries as separate files; the single EXE
extracts its embedded files to a temporary directory at startup. To use
modified libraries, rebuild with the supplied source and packaging scripts, or
use the portable package with replacement DLLs under `_internal/`. See
`docs/releasing.md` for build instructions.

PyAV's source and its FFmpeg build recipe are at
<https://github.com/PyAV-Org/PyAV/tree/v18.1.0>. No changes to these libraries
are made by the LiveTrans packaging scripts.

- Python: <https://docs.python.org/3/license.html>
- PyInstaller bootloader exception: <https://pyinstaller.org/en/stable/license.html>
- PyAV: <https://github.com/PyAV-Org/PyAV>; FFmpeg: <https://ffmpeg.org/legal.html>
- Silero VAD: <https://github.com/snakers4/silero-vad>, MIT license.

The bundled `livetrans/assets/silero_vad.onnx` is the VAD model. Whisper and
translation models are not included; their licenses apply when downloaded.
