@echo off
chcp 65001 >nul
title Exegol V3 - Workbench Launcher
cd /d "%~dp0"

echo [Exegol] Launching Workbench...
echo.

:: 0. Verify local startup configuration
echo [0/4] Verifying startup configuration...
if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment not found at .venv\Scripts\python.exe
    echo Please create the virtual environment and install requirements first.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" scripts\verify_startup.py
if %errorlevel% neq 0 (
    echo [ERROR] Startup verification failed.
    pause
    exit /b 1
)

echo Releasing stale launcher ports...
".venv\Scripts\python.exe" scripts\release_ports.py --ports 8000 3000
if %errorlevel% neq 0 (
    echo [ERROR] Failed to release stale launcher ports.
    pause
    exit /b 1
)

:: 1. Verify Docker
echo [1/4] Verifying Docker Status...
".venv\Scripts\python.exe" scripts\verify_docker.py
if %errorlevel% neq 0 (
    echo [ERROR] Docker is required for reliable Exegol sandbox execution.
    echo Start Docker Desktop, then run Start_Exegol.bat again.
    pause
    exit /b 1
)

:: 2. Start Backend
echo [2/4] Starting Backend API...
if not exist "src\api.py" (
    echo [ERROR] Backend source not found at src\api.py
    pause
    exit /b 1
)
start /min "Exegol Backend" cmd /k "set ""EXEGOL_REPO_PATH=%~dp0"" && call .venv\Scripts\activate && cd /d ""%~dp0src"" && python api.py"

echo Waiting for backend health check...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$deadline=(Get-Date).AddSeconds(45); do { try { $r=Invoke-WebRequest -UseBasicParsing 'http://127.0.0.1:8000/health' -TimeoutSec 2; if ($r.StatusCode -eq 200) { exit 0 } } catch {}; Start-Sleep -Seconds 1 } while ((Get-Date) -lt $deadline); exit 1"
if %errorlevel% neq 0 (
    echo [ERROR] Backend API did not become healthy at http://127.0.0.1:8000/health
    call Stop_Exegol.bat
    pause
    exit /b 1
)

:: 3. Start Frontend
echo [3/4] Starting Frontend UI...
if not exist "workbench_ui" (
    echo [ERROR] workbench_ui folder not found.
    pause
    exit /b 1
)

pushd workbench_ui
if not exist "node_modules\" (
    echo node_modules missing, installing...
    call npm install
    if %errorlevel% neq 0 (
        popd
        echo [ERROR] npm install failed.
        call Stop_Exegol.bat
        pause
        exit /b 1
    )
)
echo Verifying frontend install and clearing generated Next.js cache...
if exist "..\.venv\Scripts\python.exe" (
    "..\.venv\Scripts\python.exe" ..\scripts\workbench_frontend_preflight.py --mode production --repair-cache
) else (
    python ..\scripts\workbench_frontend_preflight.py --mode production --repair-cache
)
if %errorlevel% neq 0 (
    popd
    echo [ERROR] Frontend preflight failed.
    call Stop_Exegol.bat
    pause
    exit /b 1
)
echo Building production frontend...
call npm run build
if %errorlevel% neq 0 (
    popd
    echo [ERROR] Frontend production build failed.
    call Stop_Exegol.bat
    pause
    exit /b 1
)
start /min "Exegol Frontend" cmd /k "npm run start -- --hostname 127.0.0.1 --port 3000"
popd

echo Waiting for frontend UI...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$deadline=(Get-Date).AddSeconds(60); do { try { $r=Invoke-WebRequest -UseBasicParsing 'http://127.0.0.1:3000' -TimeoutSec 2; if ($r.StatusCode -lt 500) { exit 0 } } catch {}; Start-Sleep -Seconds 1 } while ((Get-Date) -lt $deadline); exit 1"
if %errorlevel% neq 0 (
    echo [ERROR] Frontend UI did not become reachable at http://127.0.0.1:3000
    call Stop_Exegol.bat
    pause
    exit /b 1
)

:: 4. Open Browser
echo [4/4] Opening browser to http://127.0.0.1:3000...
start http://127.0.0.1:3000

echo.
echo =======================================================
echo  Exegol Workbench is running.
echo  API: http://127.0.0.1:8000
echo  UI:  http://127.0.0.1:3000
echo =======================================================
echo.
echo Press any key to stop all processes and exit...
pause >nul

call Stop_Exegol.bat
exit /b 0
