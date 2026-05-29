@echo off
chcp 65001 >nul
title Exegol V3 - Workbench Shutdown
cd /d "%~dp0"

echo =======================================================
echo  EXEGOL WORKBENCH SHUTDOWN SYSTEM
echo =======================================================
echo.

echo [1/3] Closing Exegol terminal windows...
taskkill /FI "WINDOWTITLE eq Exegol Backend*" /F /T >nul 2>&1
taskkill /FI "WINDOWTITLE eq Exegol Frontend*" /F /T >nul 2>&1
taskkill /FI "WINDOWTITLE eq Exegol V3 - Workbench Launcher*" /F /T >nul 2>&1
timeout /t 1 >nul

echo [2/3] Releasing port 8000 (Backend API)...
".venv\Scripts\python.exe" scripts\release_ports.py --ports 8000

echo [3/3] Releasing port 3000 (Frontend UI)...
".venv\Scripts\python.exe" scripts\release_ports.py --ports 3000

echo.
echo =======================================================
echo  All Exegol processes and terminals are stopped.
echo =======================================================
echo.
timeout /t 2 >nul
exit
