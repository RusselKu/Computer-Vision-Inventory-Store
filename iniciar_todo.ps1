# Script de inicio en 1 clic para PowerShell
Write-Host "=====================================================================" -ForegroundColor Cyan
Write-Host "      Iniciando Sistema de Punto de Venta con Visión IA (1 Clic)     " -ForegroundColor Cyan
Write-Host "=====================================================================" -ForegroundColor Cyan
Write-Host ""

$rootDir = $PSScriptRoot

Write-Host "[1/3] Iniciando Backend API (FastAPI - Puerto 8000)..." -ForegroundColor Yellow
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$rootDir/backend'; ..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload" -WindowStyle Minimized

Write-Host "[2/3] Iniciando Frontend Dashboard y POS (Puerto 5173)..." -ForegroundColor Yellow
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$rootDir/frontend-dashboard'; npm run dev" -WindowStyle Minimized

Write-Host "[3/3] Iniciando Worker de Visión por Computadora (Cámara y Streaming)..." -ForegroundColor Yellow
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$rootDir/cv-worker'; ..\.venv\Scripts\python.exe main.py" -WindowStyle Minimized

Write-Host ""
Write-Host "Esperando 4 segundos a que los servicios se estabilicen..." -ForegroundColor Gray
Start-Sleep -Seconds 4

Write-Host "Abriendo navegador en el Panel de Control y POS..." -ForegroundColor Green
Start-Process "http://localhost:5173"

Write-Host ""
Write-Host "=====================================================================" -ForegroundColor Green
Write-Host "  ✓ ¡TODO EN MARCHA!" -ForegroundColor Green
Write-Host "  - Frontend Unificado (POS + Métricas): http://localhost:5173"
Write-Host "  - Backend FastAPI:                     http://localhost:8000"
Write-Host "  - Streaming de Cámara:                 http://localhost:8088/video_feed"
Write-Host ""
Write-Host "  * Para apagar todo ejecuta: .\detener_todo.ps1 o detener_todo.bat" -ForegroundColor Cyan
Write-Host "=====================================================================" -ForegroundColor Green
