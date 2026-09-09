@echo off
chcp 65001 >nul
title POS Computer Vision - Deteniendo Todo
echo =====================================================================
echo       Deteniendo Todos los Servicios del POS (Backend, Frontend, CV)
echo =====================================================================
echo.

echo Cerrando ventanas de servicios...
taskkill /FI "WINDOWTITLE eq POS Backend*" /F /T >nul 2>&1
taskkill /FI "WINDOWTITLE eq POS Dashboard*" /F /T >nul 2>&1
taskkill /FI "WINDOWTITLE eq POS Visión*" /F /T >nul 2>&1

echo Liberando puertos de red (8000, 5173, 8088)...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":8000.*LISTENING"') do (
    taskkill /f /pid %%a >nul 2>&1
)
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":5173.*LISTENING"') do (
    taskkill /f /pid %%a >nul 2>&1
)
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":8088.*LISTENING"') do (
    taskkill /f /pid %%a >nul 2>&1
)

echo.
echo =====================================================================
echo   ✓ Todos los servicios han sido detenidos limpiamente.
echo =====================================================================
echo.
timeout /t 3 >nul
