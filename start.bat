@echo off
rem LiveTrans dev entry: runs `tauri dev` (Vite frontend + debug shell + .venv core).
rem Release entry is the installed shortcut or livetrans.exe from the portable ZIP
rem (built by scripts\build_windows.py); do not run leftovers under target\.
rem Keep this file ASCII-only: cmd parses .bat with the OEM code page (e.g. GBK),
rem so UTF-8 comments get split into bogus commands.
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" goto no_venv
if not exist "desktop\node_modules\@tauri-apps\cli\tauri.js" goto no_node_modules

set PYTHONIOENCODING=utf-8
cd desktop
call npm run tauri:dev
cd ..
goto end

:no_venv
echo [LiveTrans] .venv not found. Run: python -m venv .venv ^& pip install -e .[cuda]
goto wait

:no_node_modules
echo [LiveTrans] desktop\node_modules not found. Run: cd desktop ^& npm ci
goto wait

:wait
pause
:end
