@echo off
REM Start only the Web Server for After Effects integration (DEBUG MODE)
REM Use this when host.py is running on a remote machine

pushd "%~dp0"

REM Check if venv exists
if not exist "venv\Scripts\python.exe" (
    echo Error: Virtual environment not found!
    echo Please create a venv first: python -m venv venv
    pause
    popd
    exit /b 1
)

echo Starting Logi web server in DEBUG mode (remote host mode)...
echo.

REM Start web_server.py in a new VISIBLE window
start "Logi Web Server" cmd /k "cd /d %~dp0 & venv\Scripts\python.exe web_server.py"

echo.
echo Logi web server started in DEBUG mode (terminal visible).
echo Host.py should be running on the remote machine.

popd
