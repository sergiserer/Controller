@echo off
rem Cierra cualquier Mando/servidor que esté ocupando el puerto 8765
powershell -NoProfile -Command "Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }"
echo Puerto 8765 liberado. Ya puedes abrir Mando.exe.
timeout /t 2 >nul
