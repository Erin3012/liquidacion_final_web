$ErrorActionPreference = "Stop"

$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectDir

Write-Host "=== Configuración HTTPS local del host ==="

if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
    throw "No se encontró winget. Instale App Installer de Microsoft y vuelva a ejecutar este script."
}

$mkcertCommand = Get-Command mkcert -ErrorAction SilentlyContinue
if (-not $mkcertCommand) {
    Write-Host "Instalando mkcert..."
    winget install --id FiloSottile.mkcert -e --accept-source-agreements --accept-package-agreements
}

$mkcertCommand = Get-Command mkcert -ErrorAction SilentlyContinue
if ($mkcertCommand) {
    $mkcertPath = $mkcertCommand.Source
} else {
    $mkcertPath = Get-ChildItem -Path "$env:LOCALAPPDATA\Microsoft\WinGet\Packages" -Recurse -Filter mkcert.exe -ErrorAction SilentlyContinue | Select-Object -First 1 -ExpandProperty FullName
}
if (-not $mkcertPath) { throw "No se encontró mkcert después de la instalación." }

Write-Host "Instalando la autoridad certificadora local..."
& $mkcertPath -install

$ipAddresses = @(Get-NetIPAddress -AddressFamily IPv4 |
    Where-Object { $_.IPAddress -notlike "127.*" -and $_.IPAddress -notlike "169.254.*" } |
    Select-Object -ExpandProperty IPAddress)
if ($ipAddresses.Count -eq 0) { throw "No se encontró una dirección IPv4 de red." }

$certDir = Join-Path $ProjectDir "certs"
New-Item -ItemType Directory -Path $certDir -Force | Out-Null

$names = @("localhost", "127.0.0.1", $env:COMPUTERNAME) + $ipAddresses
$names = @($names | Sort-Object -Unique)
$certFile = Join-Path $certDir "liquidacion-local.pem"
$keyFile = Join-Path $certDir "liquidacion-local-key.pem"

Write-Host ("Generando certificado para: " + ($names -join ", "))
& $mkcertPath -cert-file $certFile -key-file $keyFile @names

$caRoot = (& $mkcertPath -CAROOT).Trim()
Copy-Item -LiteralPath (Join-Path $caRoot "rootCA.pem") -Destination (Join-Path $certDir "rootCA.pem") -Force

try {
    if (-not (Get-NetFirewallRule -DisplayName "Liquidacion Web HTTPS 8000" -ErrorAction SilentlyContinue)) {
        New-NetFirewallRule -DisplayName "Liquidacion Web HTTPS 8000" -Direction Inbound -Protocol TCP -LocalPort 8000 -Action Allow -Profile Private | Out-Null
    }
} catch {
    Write-Warning "No se pudo crear la regla de Firewall. Ejecute este instalador como administrador si otros equipos no logran conectarse."
}

Write-Host "Reiniciando la aplicación con HTTPS..."
& (Join-Path $ProjectDir "restart_server.ps1")

Write-Host ""
Write-Host "Configuración completada."
Write-Host ("URL principal: https://" + $ipAddresses[0] + ":8000/")
Write-Host ("Certificado raíz para clientes: " + (Join-Path $certDir "rootCA.pem"))
