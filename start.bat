@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" goto no_venv
set PYTHONIOENCODING=utf-8

if exist "desktop\src-tauri\target\release\livetrans.exe" (
    start "" "desktop\src-tauri\target\release\livetrans.exe"
    goto end
)
if exist "desktop\src-tauri\target\debug\livetrans.exe" (
    start "" "desktop\src-tauri\target\debug\livetrans.exe"
    goto end
)

echo [LiveTrans] Desktop executable not built yet. Building...
cd desktop\src-tauri
cargo build --release
cd ..\..
if exist "desktop\src-tauri\target\release\livetrans.exe" (
    start "" "desktop\src-tauri\target\release\livetrans.exe"
    goto end
)
goto end
:no_venv
echo [LiveTrans] .venv not found. Run: python -m venv .venv then pip install -e .[cuda]
pause
:end
