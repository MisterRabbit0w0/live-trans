@echo off
rem LiveTrans 开发入口：以 tauri dev 启动（Vite 前端 + debug 壳 + .venv 核心）。
rem 发行产物入口：安装版开始菜单/桌面快捷方式，或便携 ZIP 中的 livetrans.exe
rem （由 scripts\build_windows.py 产出，不要直接运行 target\ 下的构建残留）。
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
