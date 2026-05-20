@echo off
:: Set code page to UTF-8 to support beautiful emojis in the terminal
chcp 65001 >nul
title Exegol V3 - Workbench Shutdown
cd /d "%~dp0"

echo =======================================================
echo  🛑  EXEGOL WORKBENCH SHUTDOWN SYSTEM
echo =======================================================
echo.

:: 1. Terminate Terminal Windows by Title (using tree-kill /t)
echo [1/3] 🧹 Closing Exegol terminal windows...
taskkill /FI "WINDOWTITLE eq Exegol Backend*" /F /T >nul 2>&1
taskkill /FI "WINDOWTITLE eq Exegol Frontend*" /F /T >nul 2>&1
taskkill /FI "WINDOWTITLE eq Exegol Supervisor*" /F /T >nul 2>&1
taskkill /FI "WINDOWTITLE eq Exegol V3 - Workbench Launcher*" /F /T >nul 2>&1
timeout /t 1 >nul

:: 2. Terminate Backend process tree on Port 8000
echo [2/3] ⚡ Releasing port 8000 (Backend API)...
set "PORT_8000_KILLED=0"
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :8000 ^| findstr LISTENING') do (
    taskkill /F /PID %%a /T >nul 2>&1
    set "PORT_8000_KILLED=1"
)
if "%PORT_8000_KILLED%"=="1" (
    echo      ✔ Port 8000 processes terminated successfully.
) else (
    echo      ℹ Port 8000 was already free.
)

:: 3. Terminate Frontend process tree on Port 3000
echo [3/3] ⚡ Releasing port 3000 (Frontend UI)...
set "PORT_3000_KILLED=0"
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :3000 ^| findstr LISTENING') do (
    taskkill /F /PID %%a /T >nul 2>&1
    set "PORT_3000_KILLED=1"
)
if "%PORT_3000_KILLED%"=="1" (
    echo      ✔ Port 3000 processes terminated successfully.
) else (
    echo      ℹ Port 3000 was already free.
)

echo.
echo =======================================================
echo  ✨ All Exegol processes and terminals are stopped!
echo =======================================================
echo.
timeout /t 2 >nul
exit
