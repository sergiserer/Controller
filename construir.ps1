# construir.ps1
# Genera Mando.exe a partir de mando_app.py + apagar_pc.py.
# Ejecútalo UNA vez en tu PC (con Python instalado):
#     powershell -ExecutionPolicy Bypass -File .\construir.ps1
# Al terminar tendrás Mando.exe en esta misma carpeta, listo para pasárselo a quien sea.

$ErrorActionPreference = "Stop"
$carpeta = $PSScriptRoot
Set-Location $carpeta

# Python
$python = (Get-Command python.exe -ErrorAction SilentlyContinue).Source
if (-not $python) { $python = (Get-Command py.exe -ErrorAction SilentlyContinue).Source }
if (-not $python) { Write-Error "No encuentro Python. Instálalo desde python.org marcando 'Add Python to PATH'."; exit 1 }

Write-Host "Instalando PyInstaller y qrcode (solo la primera vez)..." -ForegroundColor Cyan
& $python -m pip install --quiet --upgrade pyinstaller qrcode

$ico = Join-Path $carpeta "mando.ico"
$argsIcono = if (Test-Path $ico) { @("--icon", $ico) } else { @() }

Write-Host "Compilando Mando.exe..." -ForegroundColor Cyan
& $python -m PyInstaller `
    --onefile `
    --noconsole `
    --name Mando `
    --collect-submodules qrcode `
    @argsIcono `
    mando_app.py

$exe = Join-Path $carpeta "dist\Mando.exe"
if (-not (Test-Path $exe)) { Write-Error "Algo falló: no se generó Mando.exe"; exit 1 }

Copy-Item $exe (Join-Path $carpeta "Mando.exe") -Force

# Limpieza de archivos temporales de la compilación
Remove-Item (Join-Path $carpeta "build") -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item (Join-Path $carpeta "dist") -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item (Join-Path $carpeta "Mando.spec") -Force -ErrorAction SilentlyContinue

Write-Host "`nListo. Tienes Mando.exe en esta carpeta." -ForegroundColor Green
Write-Host "Pásaselo a tu amigo. Solo tiene que hacer doble clic." -ForegroundColor Green
