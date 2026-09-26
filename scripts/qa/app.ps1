# Compila y lanza la app real con el puerto de depuracion abierto, para conducirla con ui.mjs.
#
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\qa\app.ps1            # compila y lanza
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\qa\app.ps1 -NoBuild   # solo lanza
#
# La cadena de compilacion es portable y no necesita administrador: Rust en E:\rust y
# MSVC en E:\msvc (portable-msvc.py). Si estan en otro sitio, pasa -RustHome / -MsvcSetup.

param(
    [switch]$NoBuild,
    [int]$Port = 9222,
    [string]$RustHome = "E:\rust",
    [string]$MsvcSetup = "E:\msvc\msvc\setup_x64.bat"
)

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$exe = Join-Path $repo "src-tauri\target\release\kamvex.exe"

# La app, su sidecar y el motor en ejecucion bloquean el enlazado y dejan huerfanos.
Get-Process kamvex, kamvex-sidecar, llama-server -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Milliseconds 800

# El exe empaquetado por PyInstaller es lo que la app lanza: refrescarlo o se prueba el viejo.
# Hay dos copias: la que cargo empotra en el instalador (binaries\) y la que el exe de
# release lanza desde su propia carpeta (target\release\). Con -NoBuild cargo no corre,
# asi que la segunda hay que copiarla a mano o la app arranca el sidecar antiguo.
$fresh = Join-Path $repo "sidecar\dist\kamvex-sidecar.exe"
$targets = @(
    (Join-Path $repo "src-tauri\binaries\kamvex-sidecar-x86_64-pc-windows-msvc.exe"),
    (Join-Path $repo "src-tauri\target\release\kamvex-sidecar.exe")
)
foreach ($dst in $targets) {
    if ((Test-Path $fresh) -and ((-not (Test-Path $dst)) -or
        ((Get-Item $fresh).LastWriteTime -gt (Get-Item $dst).LastWriteTime))) {
        Copy-Item $fresh $dst -Force
        "sidecar actualizado: $dst ($((Get-Item $dst).Length) bytes)"
    }
}

if (-not $NoBuild) {
    $env:CARGO_HOME = Join-Path $RustHome "cargo"
    $env:RUSTUP_HOME = Join-Path $RustHome "rustup"
    $env:PATH = (Join-Path $env:CARGO_HOME "bin") + ";" + $env:PATH
    if (-not (Test-Path $MsvcSetup)) { throw "no encuentro MSVC portable: $MsvcSetup" }
    # setup_x64.bat exporta INCLUDE/LIB/PATH; se leen de vuelta a este proceso.
    $lines = cmd /c "`"$MsvcSetup`" && set"
    foreach ($line in $lines) {
        if ($line -match '^([^=]+)=(.*)$') { Set-Item -Path "env:$($matches[1])" -Value $matches[2] }
    }
    Push-Location (Join-Path $repo "src-tauri")
    try {
        # `custom-protocol` empotra dist/; sin ella el exe pide el servidor de desarrollo.
        cargo build --release --features custom-protocol
        if ($LASTEXITCODE -ne 0) { throw "cargo build fallo con codigo $LASTEXITCODE" }
    } finally { Pop-Location }
}

if (-not (Test-Path $exe)) { throw "no existe $exe" }
$env:WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS = "--remote-debugging-port=$Port"
Start-Process -FilePath $exe -WorkingDirectory (Split-Path $exe)

# Esperar a que WebView2 abra el puerto de depuracion.
$deadline = (Get-Date).AddSeconds(60)
while ((Get-Date) -lt $deadline) {
    try {
        Invoke-WebRequest -Uri "http://127.0.0.1:$Port/json/version" -UseBasicParsing -TimeoutSec 2 | Out-Null
        "app lista en CDP http://127.0.0.1:$Port"
        exit 0
    } catch { Start-Sleep -Milliseconds 700 }
}
throw "la app no abrio el puerto $Port"
