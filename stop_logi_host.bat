@echo off
REM Stop Logi Host and Web Server processes

REM Kill by window title (various patterns)
taskkill /FI "WINDOWTITLE eq Logi Web Server*" /F 2>nul
taskkill /FI "WINDOWTITLE eq Logi Host*" /F 2>nul
taskkill /FI "WINDOWTITLE eq *web_server.py*" /F 2>nul
taskkill /FI "WINDOWTITLE eq *host.py*" /F 2>nul

REM Kill Python processes running our scripts using taskkill
FOR /F "tokens=2" %%i IN ('tasklist /FI "IMAGENAME eq python.exe" /FO LIST ^| findstr "PID:"') DO (
    wmic process where "ProcessId=%%i" get CommandLine 2>nul | findstr /i "web_server.py host.py" >nul && taskkill /PID %%i /F 2>nul
)

REM Fallback: use wmic to find and kill by command line
wmic process where "commandline like '%%web_server.py%%'" call terminate 2>nul
wmic process where "commandline like '%%host.py%%'" call terminate 2>nul

REM Also try killing any cmd.exe windows that spawned our scripts
wmic process where "commandline like '%%Logi Web Server%%'" call terminate 2>nul
wmic process where "commandline like '%%Logi Host%%'" call terminate 2>nul

echo Logi services stopped.
