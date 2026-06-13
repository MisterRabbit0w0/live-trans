@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" goto no_venv
set PYTHONIOENCODING=utf-8
start "" ".venv\Scripts\pythonw.exe" -m livetrans.main
goto end
:no_venv
echo [LiveTrans] .venv not found. Run: python -m venv .venv then pip install -e .[cuda]
pause
:end
