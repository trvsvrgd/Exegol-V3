@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo [Exegol V3] Launching Model Workbench...

:: 0. Verify Docker
echo [0/3] Verifying Docker Status...
if exist ".venv\Scripts\activate" (
    call .venv\Scripts\activate & python scripts\verify_docker.py
) else (
    python scripts\verify_docker.py
)
if %errorlevel% neq 0 (
    echo [WARNING] Docker is not running. Sandbox features may be limited.
    echo Continuing startup anyway...
)

:: 1. Releasing stale ports
echo Releasing stale ports...
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" scripts\release_ports.py --ports 8000 3000
) else (
    python scripts\release_ports.py --ports 8000 3000
)

:: 2. Start Backend API
if not exist "src\api.py" (
    echo [ERROR] Backend source not found at src\api.py
    pause
    exit /b
)
if exist ".venv\Scripts\activate" (
    start "Exegol Backend" cmd /k "call .venv\Scripts\activate && cd src && python api.py"
) else (
    start "Exegol Backend" cmd /k "cd src && python api.py"
)

:: 3. Start Next.js Frontend
if not exist "workbench_ui" (
    echo [ERROR] workbench_ui folder not found.
    pause
    exit /b
)

pushd workbench_ui
if not exist "node_modules\" (
    echo node_modules missing, installing...
    call npm install
)
echo Verifying frontend install and clearing generated Next.js dev cache...
if exist "..\.venv\Scripts\python.exe" (
    "..\.venv\Scripts\python.exe" ..\scripts\workbench_frontend_preflight.py --mode development --repair-cache
) else (
    python ..\scripts\workbench_frontend_preflight.py --mode development --repair-cache
)
if %errorlevel% neq 0 (
    popd
    echo [ERROR] Frontend preflight failed.
    pause
    exit /b 1
)
start "Exegol Frontend" cmd /k "npm run dev -- --hostname 127.0.0.1 --port 3000"
popd

echo Workbench is launching. 
echo API: http://localhost:8000
echo UI: http://127.0.0.1:3000

:: 4. Wait for Frontend UI and Open Browser
echo Waiting for frontend UI...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$deadline=(Get-Date).AddSeconds(75); do { try { $r=Invoke-WebRequest -UseBasicParsing 'http://127.0.0.1:3000' -TimeoutSec 3; if ($r.StatusCode -lt 500) { exit 0 } } catch {}; Start-Sleep -Seconds 1 } while ((Get-Date) -lt $deadline); exit 1"

if %errorlevel% equ 0 (
    echo Opening browser to http://127.0.0.1:3000...
    start http://127.0.0.1:3000
) else (
    echo [WARNING] Frontend UI did not become reachable at http://127.0.0.1:3000 in time.
)
