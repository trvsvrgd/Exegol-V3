@echo off
title Exegol V3 - Workbench Launcher
echo [Exegol] Launching Workbench...

:: 1. Start Backend (Minimized)
echo [1/3] Starting Backend API...
start /min "Exegol Backend" cmd /c "call .venv\Scripts\activate & cd src & python api.py"

:: 2. Start Frontend (Minimized)
echo [2/3] Starting Frontend UI...
cd workbench_ui
if not exist "node_modules\" (
    echo node_modules missing, installing...
    call npm install
)
start /min "Exegol Frontend" cmd /c "npm run dev"
cd ..

:: 3. Open Browser
echo [3/3] Opening browser to http://localhost:3000...
timeout /t 3 >nul
start http://localhost:3000

echo.
echo =======================================================
echo  🚀 Exegol Workbench is now running in the background.
echo  API: http://localhost:8000
echo  UI:  http://localhost:3000
echo =======================================================
echo.
echo Press any key to stop all processes and exit...
pause >nul

:: Cleanup
taskkill /FI "WINDOWTITLE eq Exegol Backend*" /F >nul 2>&1
taskkill /FI "WINDOWTITLE eq Exegol Frontend*" /F >nul 2>&1
echo [Exegol] Shutdown complete.
exit
