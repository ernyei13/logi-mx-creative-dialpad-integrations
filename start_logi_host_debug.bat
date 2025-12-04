@echo off
REM Start Logi Host and Web Server for After Effects integration (DEBUG MODE)
REM This script shows terminal windows for debugging

pushd "%~dp0"

REM Check if venv exists
if not exist "venv\Scripts\python.exe" (
    echo Error: Virtual environment not found!
    echo Please create a venv first: python -m venv venv
    pause
    popd
    exit /b 1
)

echo Starting Logi services in DEBUG mode...
echo.

REM Start web_server.py in a new VISIBLE window
start "Logi Web Server" cmd /k "cd /d %~dp0 & venv\Scripts\python.exe web_server.py"

REM Give the web server a moment to start
echo Waiting for web server to start...
timeout /t 3 /nobreak > nul

REM Start host.py in a new VISIBLE window
start "Logi Host" cmd /k "cd /d %~dp0 & venv\Scripts\python.exe host.py"

echo.
echo Logi services started in DEBUG mode (terminals visible).
echo Select devices manually in the Logi Host window.
echo.

popd
