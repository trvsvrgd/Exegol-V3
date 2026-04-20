@echo off
echo [Exegol V3] Launching Model Workbench...

:: Start Backend API
start cmd /k "cd src && python api.py"

:: Start Next.js Frontend
start cmd /k "cd workbench_ui && npm run dev"

echo Workbench is launching. 
echo API: http://localhost:8000
echo UI: http://localhost:3000
