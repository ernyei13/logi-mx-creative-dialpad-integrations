@echo off
REM Start Logi Host and Web Server for After Effects integration (HEADLESS)
REM This script returns immediately - processes run in background

pushd "%~dp0"

REM Check if venv exists
if not exist "venv\Scripts\python.exe" (
    popd
    exit /b 1
)

REM Start web_server.py minimized (auto-select localhost)
start "" /min cmd /c "cd /d %~dp0 && echo 1 | venv\Scripts\python.exe web_server.py"

REM Start host.py minimized with auto mode (no wait)
start "" /min cmd /c "cd /d %~dp0 && echo 127.0.0.1 | venv\Scripts\python.exe host.py --auto"

popd
exit /b 0
