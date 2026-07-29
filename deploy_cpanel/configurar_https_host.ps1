$ErrorActionPreference = "Stop"
$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectDir
if (-not (Get-Command winget -ErrorAction SilentlyContinue)) { throw "No se encontró winget." }
$mkcertCommand = Get-Command mkcert -ErrorAction SilentlyContinue
if (-not $mkcertCommand) { winget install --id FiloSottile.mkcert -e --accept-source-agreements --accept-package-agreements }
$mkcertCommand = Get-Command mkcert -ErrorAction SilentlyContinue
$mkcertPath = if ($mkcertCommand) { $mkcertCommand.Source } else { Get-ChildItem -Path "$env:LOCALAPPDATA\Microsoft\WinGet\Packages" -Recurse -Filter mkcert.exe -ErrorAction SilentlyContinue | Select-Object -First 1 -ExpandProperty FullName }
if (-not $mkcertPath) { throw "No se encontró mkcert." }
& $mkcertPath -install
$ips = @(Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -notlike "127.*" -and $_.IPAddress -notlike "169.254.*" } | Select-Object -ExpandProperty IPAddress)
if ($ips.Count -eq 0) { throw "No se encontró una dirección IPv4 de red." }
$certDir = Join-Path $ProjectDir "certs"; New-Item -ItemType Directory -Path $certDir -Force | Out-Null
$names = @(@("localhost", "127.0.0.1", $env:COMPUTERNAME) + $ips | Sort-Object -Unique)
& $mkcertPath -cert-file (Join-Path $certDir "liquidacion-local.pem") -key-file (Join-Path $certDir "liquidacion-local-key.pem") @names
Copy-Item -LiteralPath (Join-Path ((& $mkcertPath -CAROOT).Trim()) "rootCA.pem") -Destination (Join-Path $certDir "rootCA.pem") -Force
try { if (-not (Get-NetFirewallRule -DisplayName "Liquidacion Web HTTPS 8000" -ErrorAction SilentlyContinue)) { New-NetFirewallRule -DisplayName "Liquidacion Web HTTPS 8000" -Direction Inbound -Protocol TCP -LocalPort 8000 -Action Allow -Profile Private | Out-Null } } catch { Write-Warning "No se pudo crear la regla de Firewall. Ejecute como administrador si es necesario." }
& (Join-Path $ProjectDir "restart_server.ps1")
Write-Host ("HTTPS configurado. IP principal: https://" + $ips[0] + ":8000/")
