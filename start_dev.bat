@echo off
cd /d "%~dp0"

:: Kiem tra va khoi dong MQTT Broker neu chua chay
start "MQTT Broker" /min powershell -NoProfile -ExecutionPolicy Bypass -Command "$port = 1884; if (-not (Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue)) { $svc = Get-Service -Name 'mosquitto' -ErrorAction SilentlyContinue; if ($svc -and $svc.Status -ne 'Running') { Start-Service -Name 'mosquitto'; Start-Sleep -Seconds 3 } }; if (Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue) { Write-Host 'MQTT broker is listening on port 1884.' } else { Write-Host 'MQTT broker is NOT listening on port 1884.'; Start-Sleep -Seconds 3 }; exit"

start "Backend" powershell -NoExit -ExecutionPolicy Bypass -Command "Set-Location '%~dp0'; & '.venv\Scripts\Activate.ps1'; python -m uvicorn --app-dir backend app.main:app --reload --host 0.0.0.0 --port 8000"

start "Frontend" powershell -NoExit -Command "Set-Location '%~dp0'; npm --prefix frontend run dev"

start "AI Edge" powershell -NoExit -ExecutionPolicy Bypass -Command "Set-Location '%~dp0'; & '.venv\Scripts\Activate.ps1'; $env:PYTHONPATH = '%~dp0edge-ai'; python 'edge-ai\main.py'"

exit /b
