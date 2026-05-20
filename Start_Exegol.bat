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

:: 1. Start Supervisor (Backend + Frontend, log rotation, hung-start detection)
echo [1/3] Starting process supervisor...
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

:: 2. Verify Frontend Dependencies
echo [2/3] Verifying Frontend UI dependencies...
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
popd

if not exist ".exegol\logs" mkdir ".exegol\logs"
start /min "Exegol Supervisor" cmd /c "call .venv\Scripts\activate & python scripts\supervisor.py --repo-root ""%CD%"""


:: 3. Verify Startup and Open Browser
echo [3/3] Verifying startup contract...
timeout /t 5 >nul
call .venv\Scripts\activate & python scripts\verify_startup.py --repo-path "%CD%"
if %errorlevel% neq 0 (
    echo [WARNING] Startup verification reported degraded state. See .exegol\logs\backend.log and .exegol\logs\frontend.log.
)
start http://localhost:3000

echo.
echo =======================================================
echo  🚀 Exegol Workbench is now running in the background.
echo  API: http://localhost:8000
echo  UI:  http://localhost:3000
echo  Logs: .exegol\logs\backend.log and .exegol\logs\frontend.log
echo =======================================================
echo.
echo Press any key to stop all processes and exit...
pause >nul

:: Cleanup
call Stop_Exegol.bat
exit
