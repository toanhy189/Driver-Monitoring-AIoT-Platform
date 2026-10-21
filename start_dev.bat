```bat
@echo off
cd /d "%~dp0"

start "Backend" powershell -NoExit -Command "Set-Location '%~dp0'; conda activate iot-env; python -m uvicorn --app-dir backend app.main:app --reload --host 0.0.0.0 --port 8000 "

start "Frontend" powershell -NoExit -Command "Set-Location '%~dp0'; npm --prefix frontend run dev"

start "AI Edge" powershell -NoExit -Command "Set-Location '%~dp0'; $env:PYTHONPATH = '%~dp0edge-ai'; conda activate iot-env; python 'edge-ai\main.py' "

exit /b
```