$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Python = Join-Path $Root ".venv\Scripts\python.exe"
$CargoBin = Join-Path $env:USERPROFILE ".cargo\bin"

if (Test-Path (Join-Path $CargoBin "cargo.exe")) {
  $env:Path = "$CargoBin;$env:Path"
}

if (-not (Get-Command cargo -ErrorAction SilentlyContinue)) {
  Write-Host "Rust/Cargo ainda nao esta instalado." -ForegroundColor Yellow
  Write-Host "Instale o Rust em https://rustup.rs/ e rode este script novamente." -ForegroundColor Cyan
  pause
  exit 1
}

if (-not (Test-Path $Python)) {
  Write-Host "Nao encontrei o ambiente virtual em: $Python" -ForegroundColor Red
  Write-Host "Execute o guia de instalacao do README antes de iniciar o Tauri." -ForegroundColor Yellow
  pause
  exit 1
}

$env:NEGOCIADORES_ROOT = $Root
$env:NEGOCIADORES_PYTHON = $Python

Set-Location $Root

if (-not (Test-Path "node_modules")) {
  Write-Host "Instalando dependencias NPM do Tauri..." -ForegroundColor Cyan
  npm install
}

Write-Host "Iniciando Monitoramento PD em modo Tauri..." -ForegroundColor Cyan
npm run tauri:dev
