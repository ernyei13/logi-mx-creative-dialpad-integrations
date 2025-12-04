@echo off
REM Stop Logi Host and Web Server processes
taskkill /FI "WINDOWTITLE eq Logi Web Server*" /F 2>nul
taskkill /FI "WINDOWTITLE eq Logi Host*" /F 2>nul
REM Also kill by python process running our scripts
wmic process where "commandline like '%%web_server.py%%'" delete 2>nul
wmic process where "commandline like '%%host.py%%'" delete 2>nul
echo Logi services stopped.
