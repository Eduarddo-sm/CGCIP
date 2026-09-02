$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = Join-Path $Root ".venv\Scripts\python.exe"
$App = Join-Path $Root "app.py"
$Cert = Join-Path $Root "data\certs\negociadores-local.crt"
$Key = Join-Path $Root "data\certs\negociadores-local.key"
$Port = 8765
$MachineName = [System.Net.Dns]::GetHostName()
$NetworkIp = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
  Where-Object {
    $_.IPAddress -notlike "127.*" -and
    $_.IPAddress -notlike "169.254.*" -and
    $_.InterfaceAlias -notmatch "Loopback|vEthernet|Bluetooth"
  } |
  Sort-Object @{ Expression = { if ($_.InterfaceAlias -eq "Ethernet") { 0 } else { 1 } } } |
  Select-Object -First 1 -ExpandProperty IPAddress

if (-not (Test-Path $App)) {
  Write-Host "Nao encontrei app.py na pasta do programa: $Root" -ForegroundColor Red
  pause
  exit 1
}

if (-not (Test-Path $Python)) {
  Write-Host "Ambiente virtual nao encontrado em: $Python" -ForegroundColor Red
  Write-Host "Crie o .venv e instale requirements.txt antes de iniciar." -ForegroundColor Yellow
  pause
  exit 1
}

Write-Host "Validando certificado HTTPS local..." -ForegroundColor DarkCyan
& $Python (Join-Path $Root "scripts\generate_https_cert.py") *> $null
if ($LASTEXITCODE -ne 0 -or -not (Test-Path $Cert) -or -not (Test-Path $Key)) {
  Write-Host "Nao foi possivel gerar o certificado HTTPS." -ForegroundColor Red
  pause
  exit 1
}

$env:NEGOCIADORES_SSL_CERT = $Cert
$env:NEGOCIADORES_SSL_KEY = $Key
$env:NEGOCIADORES_HOST = "0.0.0.0"
$env:NEGOCIADORES_PORT = "$Port"

Write-Host ""
Write-Host "Iniciando programa..." -ForegroundColor Cyan
Write-Host "Local: https://127.0.0.1:$Port"
Write-Host "Nome:  https://${MachineName}:$Port"
if ($NetworkIp) {
  Write-Host "Rede:  https://${NetworkIp}:$Port"
}
Write-Host ""
Write-Host "Deixe esta janela aberta enquanto estiver usando o sistema." -ForegroundColor Yellow
Write-Host "Para parar, pressione Ctrl+C."
Write-Host ""

Set-Location $Root
& $Python $App

Write-Host ""
Write-Host "Programa finalizado."
pause
