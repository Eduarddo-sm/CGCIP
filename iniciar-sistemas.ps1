$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$GerencialRoot = Join-Path $Root "aplicacao-gerencial"
$NegocialRoot = Join-Path $Root "aplicacao-negocial"

$GerencialPort = 8765
$NegocialPort = 8890

$PythonGerencial = Join-Path $GerencialRoot ".venv\Scripts\python.exe"
$PythonNegocial = Join-Path $NegocialRoot ".venv\Scripts\python.exe"
$GerencialApp = Join-Path $GerencialRoot "app.py"
$GerencialCert = Join-Path $GerencialRoot "data\certs\negociadores-local.crt"
$GerencialKey = Join-Path $GerencialRoot "data\certs\negociadores-local.key"

function Normalize-ProcessPath {
  $pathValue = [Environment]::GetEnvironmentVariable("Path", "Process")
  if (-not $pathValue) {
    $pathValue = [Environment]::GetEnvironmentVariable("PATH", "Process")
  }

  [Environment]::SetEnvironmentVariable("PATH", $null, "Process")
  if ($pathValue) {
    [Environment]::SetEnvironmentVariable("Path", $pathValue, "Process")
  }
}

function Stop-PortListeners {
  param([int[]] $Ports)

  foreach ($port in $Ports) {
    $owners = @(Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue |
      Where-Object { $_.OwningProcess -gt 0 } |
      Select-Object -ExpandProperty OwningProcess -Unique)

    $netstatOwners = @()
    try {
      $netstatOwners = netstat -ano |
        Select-String -Pattern "LISTENING" |
        ForEach-Object {
          $line = $_.Line.Trim()
          if ($line -match "^\s*TCP\s+\S+:$port\s+\S+\s+LISTENING\s+(\d+)\s*$") {
            [int]$Matches[1]
          }
        }
    } catch {
      $netstatOwners = @()
    }

    $owners = @($owners + $netstatOwners) |
      Where-Object { $_ -and $_ -gt 0 } |
      Sort-Object -Unique

    foreach ($owner in $owners) {
      Write-Host "Encerrando processo antigo na porta $port (PID $owner)..." -ForegroundColor Yellow
      Stop-Process -Id $owner -Force -ErrorAction SilentlyContinue
    }
  }
}

function Get-LanIp {
  $addresses = @(Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
    Where-Object {
      $_.IPAddress -notlike "127.*" -and
      $_.IPAddress -notlike "169.254.*" -and
      $_.IPAddress -notlike "0.*"
    } |
    Sort-Object -Property InterfaceMetric, InterfaceIndex)

  $preferred = $addresses | Where-Object { $_.IPAddress -like "192.168.*" } | Select-Object -First 1
  if (-not $preferred) {
    $preferred = $addresses | Select-Object -First 1
  }

  if ($preferred) {
    return $preferred.IPAddress
  }

  return "SEU-IP"
}

function Test-Health {
  param(
    [string] $Name,
    [string] $Url
  )

  for ($attempt = 1; $attempt -le 12; $attempt++) {
    try {
      if ($Url.StartsWith("https://")) {
        & curl.exe -k -sS --fail --max-time 3 $Url *> $null
        if ($LASTEXITCODE -ne 0) {
          throw "Health check HTTPS falhou."
        }
      } else {
        Invoke-RestMethod -Uri $Url -TimeoutSec 3 | Out-Null
      }
      Write-Host "$Name OK: $Url" -ForegroundColor Green
      return $true
    } catch {
      Start-Sleep -Seconds 1
    }
  }

  Write-Host "$Name nao respondeu em: $Url" -ForegroundColor Red
  return $false
}

function Get-PostgresTool {
  param([string] $Name)

  $command = Get-Command "$Name.exe" -ErrorAction SilentlyContinue
  if ($command) {
    return $command.Source
  }

  $installRoot = "C:\Program Files\PostgreSQL"
  if (Test-Path -LiteralPath $installRoot) {
    $candidate = Get-ChildItem -LiteralPath $installRoot -Directory |
      Sort-Object Name -Descending |
      ForEach-Object { Join-Path $_.FullName "bin\$Name.exe" } |
      Where-Object { Test-Path -LiteralPath $_ } |
      Select-Object -First 1
    if ($candidate) {
      return $candidate
    }
  }

  return $null
}

function Test-PostgresReady {
  $pgIsReady = Get-PostgresTool "pg_isready"
  if (-not $pgIsReady) { return $false }

  & $pgIsReady -h 127.0.0.1 -p 5432 *> $null
  return $LASTEXITCODE -eq 0
}

function Ensure-Postgres {
  if (Test-PostgresReady) {
    Write-Host "PostgreSQL OK: 127.0.0.1:5432" -ForegroundColor Green
    return
  }

  Write-Host "PostgreSQL parado. Tentando iniciar o servico..." -ForegroundColor Yellow
  $postgresService = Get-Service -Name "postgresql*" -ErrorAction SilentlyContinue |
    Sort-Object Name -Descending |
    Select-Object -First 1
  if ($postgresService) {
    try {
      Start-Service -Name $postgresService.Name -ErrorAction Stop
    } catch {
      Write-Host "Nao foi possivel iniciar o servico PostgreSQL automaticamente." -ForegroundColor Yellow
    }
  }

  for ($attempt = 1; $attempt -le 5; $attempt++) {
    if (Test-PostgresReady) {
      Write-Host "PostgreSQL iniciado com sucesso." -ForegroundColor Green
      return
    }
    Start-Sleep -Seconds 1
  }

  throw "PostgreSQL nao esta acessivel em 127.0.0.1:5432. Inicie o servico e tente novamente."
}

Normalize-ProcessPath

Ensure-Postgres

if (-not (Test-Path -LiteralPath $GerencialRoot)) {
  throw "Pasta do Gerencial nao encontrada: $GerencialRoot"
}

if (-not (Test-Path -LiteralPath $NegocialRoot)) {
  throw "Pasta do Negocial nao encontrada: $NegocialRoot"
}

if (-not (Test-Path -LiteralPath $PythonGerencial)) {
  throw "Python do Gerencial nao encontrado: $PythonGerencial"
}

if (-not (Test-Path -LiteralPath $PythonNegocial)) {
  throw "Python do Negocial nao encontrado: $PythonNegocial"
}

if (-not (Test-Path -LiteralPath $GerencialApp)) {
  throw "app.py do Gerencial nao encontrado: $GerencialApp"
}

Write-Host ""
Write-Host "Iniciando Projeto Negocial..." -ForegroundColor Cyan

Stop-PortListeners -Ports @($GerencialPort, $NegocialPort)
Start-Sleep -Seconds 2

Write-Host "Validando certificado HTTPS local do Gerencial..." -ForegroundColor DarkCyan
& $PythonGerencial (Join-Path $GerencialRoot "scripts\generate_https_cert.py") *> $null
if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $GerencialCert) -or -not (Test-Path -LiteralPath $GerencialKey)) {
  throw "Nao foi possivel gerar o certificado HTTPS do Gerencial."
}
$env:NEGOCIADORES_SSL_CERT = $GerencialCert
$env:NEGOCIADORES_SSL_KEY = $GerencialKey
$env:NEGOCIADORES_HOST = "0.0.0.0"
$env:NEGOCIADORES_PORT = "$GerencialPort"
$env:PYTHONUNBUFFERED = "1"

$GerencialOut = Join-Path $GerencialRoot "gerencial-postgres.out.log"
$GerencialErr = Join-Path $GerencialRoot "gerencial-postgres.err.log"
$NegocialOut = Join-Path $NegocialRoot "negocial-postgres.out.log"
$NegocialErr = Join-Path $NegocialRoot "negocial-postgres.err.log"

$gerencialProcess = Start-Process `
  -FilePath $PythonGerencial `
  -ArgumentList "`"$GerencialApp`"" `
  -WorkingDirectory $GerencialRoot `
  -RedirectStandardOutput $GerencialOut `
  -RedirectStandardError $GerencialErr `
  -WindowStyle Hidden `
  -PassThru

Set-Content -Path (Join-Path $GerencialRoot "server.pid") -Value $gerencialProcess.Id

$negocialProcess = Start-Process `
  -FilePath $PythonNegocial `
  -ArgumentList @("-m", "uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "$NegocialPort", "--no-access-log") `
  -WorkingDirectory $NegocialRoot `
  -RedirectStandardOutput $NegocialOut `
  -RedirectStandardError $NegocialErr `
  -WindowStyle Hidden `
  -PassThru

Set-Content -Path (Join-Path $NegocialRoot "server.pid") -Value $negocialProcess.Id

$ip = Get-LanIp

Write-Host ""
Write-Host "Processos iniciados:" -ForegroundColor Cyan
Write-Host "Gerencial PID: $($gerencialProcess.Id)"
Write-Host "Negocial  PID: $($negocialProcess.Id)"
Write-Host ""
Write-Host "Validando servidores..." -ForegroundColor Cyan

$gerencialOk = Test-Health -Name "Gerencial" -Url "https://127.0.0.1:$GerencialPort/api/health"
$negocialOk = Test-Health -Name "Negocial" -Url "http://127.0.0.1:$NegocialPort/api/health"

Write-Host ""
if ($gerencialOk -and $negocialOk) {
  Write-Host "Sistemas online na intranet:" -ForegroundColor Green
} else {
  Write-Host "Algum sistema nao respondeu. Confira os logs abaixo:" -ForegroundColor Yellow
}

Write-Host "Gerencial: https://$ip`:$GerencialPort"
Write-Host "Negocial:  http://$ip`:$NegocialPort"
Write-Host ""
Write-Host "Logs:" -ForegroundColor DarkCyan
Write-Host "Gerencial: $GerencialOut"
Write-Host "Gerencial erros: $GerencialErr"
Write-Host "Negocial:  $NegocialOut"
Write-Host "Negocial erros:  $NegocialErr"
Write-Host ""
