@echo off
chcp 65001 >nul
title POS Computer Vision - Iniciando Todo
echo =====================================================================
echo       Iniciando Sistema de Punto de Venta con Visión IA (1 Clic)
echo =====================================================================
echo.

set ROOT_DIR=%~dp0
cd /d "%ROOT_DIR%"

echo [1/3] Iniciando Backend API (FastAPI - Puerto 8000)...
start "POS Backend (FastAPI)" /min cmd /k "chcp 65001 >nul && cd /d "%ROOT_DIR%backend" && ..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload"

echo [2/3] Iniciando Frontend Dashboard y POS (Puerto 5173)...
start "POS Dashboard Frontend" /min cmd /k "chcp 65001 >nul && cd /d "%ROOT_DIR%frontend-dashboard" && npm run dev"

echo [3/3] Iniciando Worker de Visión por Computadora (Cámara y Streaming 8088)...
start "POS Visión por Computadora" /min cmd /k "chcp 65001 >nul && cd /d "%ROOT_DIR%cv-worker" && ..\.venv\Scripts\python.exe main.py"

echo.
echo Esperando 4 segundos a que los servicios respondan...
timeout /t 4 /nobreak >nul

echo.
echo Abriendo navegador en el Panel de Control y POS...
start http://localhost:5173

echo.
echo =====================================================================
echo   ✓ ¡TODO EN MARCHA!
echo   - Frontend Unificado (POS + Métricas): http://localhost:5173
echo   - Backend FastAPI:                     http://localhost:8000
echo   - Streaming de Cámara:                 http://localhost:8088/video_feed
echo.
echo   * Las ventanas secundarias se ejecutaron minimizadas para no molestar.
echo   * Para apagar todo de golpe, solo ejecuta: detener_todo.bat
echo =====================================================================
echo.
pause
