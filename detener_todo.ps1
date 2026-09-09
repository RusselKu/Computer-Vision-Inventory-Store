# Script de apagado limpio para PowerShell
Write-Host "=====================================================================" -ForegroundColor Yellow
Write-Host "       Deteniendo Todos los Servicios del POS (Backend, Frontend, CV)" -ForegroundColor Yellow
Write-Host "=====================================================================" -ForegroundColor Yellow
Write-Host ""

$ports = @(8000, 5173, 8088)

foreach ($port in $ports) {
    try {
        $conns = Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue
        if ($conns) {
            foreach ($conn in $conns) {
                $pidToKill = $conn.OwningProcess
                if ($pidToKill -and $pidToKill -ne 0) {
                    Write-Host "Cerrando proceso en puerto $port (PID: $pidToKill)..." -ForegroundColor Gray
                    Stop-Process -Id $pidToKill -Force -ErrorAction SilentlyContinue
                }
            }
        }
    } catch {
        # ignorar errores de acceso
    }
}

Write-Host ""
Write-Host "=====================================================================" -ForegroundColor Green
Write-Host "  ✓ Todos los servicios han sido detenidos limpiamente." -ForegroundColor Green
Write-Host "=====================================================================" -ForegroundColor Green
