@echo off
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

:: Start Backend API
if not exist "src\api.py" (
    echo [ERROR] Backend source not found at src\api.py
    pause
    exit /b
)
start "Exegol Backend" cmd /k "cd src && python api.py"

:: Start Next.js Frontend
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
start "Exegol Frontend" cmd /k "npm run dev"
popd

echo Workbench is launching. 
echo API: http://localhost:8000
echo UI: http://localhost:3000
