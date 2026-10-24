# crear_accesos.ps1
# Crea accesos directos para arrancar y detener apagar_pc.py sin ventana de consola.
# Ponlo en la MISMA carpeta que apagar_pc.py y ejecútalo:
#     powershell -ExecutionPolicy Bypass -File crear_accesos.ps1            (escritorio)
#     powershell -ExecutionPolicy Bypass -File crear_accesos.ps1 -Inicio    (escritorio + arranque con Windows)

param([switch]$Inicio)

$carpeta = $PSScriptRoot
$script  = Join-Path $carpeta "apagar_pc.py"
if (-not (Test-Path $script)) {
    Write-Error "No encuentro apagar_pc.py en $carpeta"; exit 1
}

# pythonw.exe = Python sin consola. pyw.exe = el lanzador equivalente.
$pythonw = (Get-Command pythonw.exe -ErrorAction SilentlyContinue).Source
if (-not $pythonw) { $pythonw = (Get-Command pyw.exe -ErrorAction SilentlyContinue).Source }
if (-not $pythonw) {
    Write-Error "No encuentro pythonw.exe ni pyw.exe. ¿Python está instalado y en el PATH?"; exit 1
}

$shell      = New-Object -ComObject WScript.Shell
$escritorio = [Environment]::GetFolderPath("Desktop")
# Iconos del mando (mando.ico y mando_detener.ico, junto a este script).
# Si no están, se usa el icono de apagado de Windows.
$iconoWindows = "$env:SystemRoot\System32\shell32.dll,27"
$icoIniciar   = Join-Path $carpeta "mando.ico"
$icoDetener   = Join-Path $carpeta "mando_detener.ico"
$iconoIniciar = if (Test-Path $icoIniciar) { "$icoIniciar,0" } else { $iconoWindows }
$iconoDetener = if (Test-Path $icoDetener) { "$icoDetener,0" } else { $iconoWindows }

function Nuevo-Acceso($ruta, $destino, $argumentos, $descripcion, $icono) {
    $lnk = $shell.CreateShortcut($ruta)
    $lnk.TargetPath       = $destino
    $lnk.Arguments        = $argumentos
    $lnk.WorkingDirectory = $carpeta
    $lnk.IconLocation     = $icono
    $lnk.Description      = $descripcion
    $lnk.WindowStyle      = 7   # minimizado
    $lnk.Save()
    Write-Host "Creado: $ruta"
}

# 1) Arrancar el servidor
$argsArrancar = "`"$script`""
Nuevo-Acceso (Join-Path $escritorio "Mando - Iniciar.lnk") $pythonw $argsArrancar "Inicia el servidor para apagar el PC desde el móvil" $iconoIniciar

# 2) Detener el servidor (busca el proceso python que ejecuta apagar_pc.py y lo cierra)
$argsDetener = '-NoProfile -WindowStyle Hidden -Command "Get-CimInstance Win32_Process | Where-Object { $_.Name -like ''python*'' -and $_.CommandLine -like ''*apagar_pc.py*'' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"'
Nuevo-Acceso (Join-Path $escritorio "Mando - Detener.lnk") "powershell.exe" $argsDetener "Detiene el servidor de apagado remoto" $iconoDetener

# 3) Opcional: arrancar automáticamente al iniciar sesión
if ($Inicio) {
    $carpetaInicio = [Environment]::GetFolderPath("Startup")
    Nuevo-Acceso (Join-Path $carpetaInicio "Mando - Iniciar.lnk") $pythonw $argsArrancar "Inicia el servidor para apagar el PC desde el móvil" $iconoIniciar
}

# Refresca la caché de iconos para que se vean los nuevos sin reiniciar
Start-Process -FilePath "ie4uinit.exe" -ArgumentList "-show" -WindowStyle Hidden -ErrorAction SilentlyContinue

Write-Host "`nListo. La URL para el iPhone es http://<IP-del-PC>:8765/?t=<token> (el token está en token.txt)."
