@echo off
title Exegol V3 - Workbench Launcher
cd /d "%~dp0"
echo [Exegol] Launching Workbench...

:: 0. Verify Docker
echo [0/3] Verifying Docker Status...
call .venv\Scripts\activate & python scripts\verify_docker.py
if %errorlevel% neq 0 (
    echo [WARNING] Docker is not running. Sandbox features may be limited.
    echo Continuing startup anyway...
)

:: 1. Start Backend (Minimized)
echo [1/3] Starting Backend API...
if not exist ".venv\Scripts\activate" (
    echo [ERROR] Virtual environment not found at .venv\Scripts\activate
    echo Please ensure you are running this from the project root.
    pause
    exit /b
)
if not exist "src\api.py" (
    echo [ERROR] Backend source not found at src\api.py
    pause
    exit /b
)
start /min "Exegol Backend" cmd /c "call .venv\Scripts\activate & cd src & python api.py"

:: 2. Start Frontend (Minimized)
echo [2/3] Starting Frontend UI...
if not exist "workbench_ui" (
    echo [ERROR] workbench_ui folder not found.
    echo Please ensure you are running this from the project root.
    pause
    exit /b
)

pushd workbench_ui
if not exist "node_modules\" (
    echo node_modules missing, installing...
    call npm install
)
start /min "Exegol Frontend" cmd /c "npm run dev"
popd


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
