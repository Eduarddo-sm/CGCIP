$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Python = Join-Path $Root ".venv\Scripts\python.exe"
$Output = Join-Path $Root "backend_dist"
$Name = "monitoramento-backend"

if (-not (Test-Path $Python)) {
  Write-Host "Nao encontrei o ambiente virtual em: $Python" -ForegroundColor Red
  Write-Host "Execute o guia de instalacao do README antes de gerar o sidecar." -ForegroundColor Yellow
  exit 1
}

Set-Location $Root

& $Python -m PyInstaller --version | Out-Null
if ($LASTEXITCODE -ne 0) {
  Write-Host "Instalando PyInstaller no Python do projeto..." -ForegroundColor Cyan
  & $Python -m pip install pyinstaller
  if ($LASTEXITCODE -ne 0) {
    Write-Host "Falha ao instalar PyInstaller." -ForegroundColor Red
    exit 1
  }
}

if (Test-Path $Output) {
  Remove-Item -LiteralPath $Output -Recurse -Force
}

Write-Host "Gerando backend sidecar..." -ForegroundColor Cyan
& $Python -m PyInstaller `
  --noconfirm `
  --clean `
  --onefile `
  --windowed `
  --name $Name `
  --distpath $Output `
  --workpath (Join-Path $Root "build\pyinstaller") `
  --specpath (Join-Path $Root "build") `
  --add-data "$Root\ui;ui" `
  --collect-submodules win32com `
  --hidden-import pythoncom `
  --hidden-import pywintypes `
  --hidden-import win32timezone `
  app.py

$Exe = Join-Path $Output "$Name.exe"
if (-not (Test-Path $Exe)) {
  Write-Host "Falha: sidecar nao foi gerado em $Exe" -ForegroundColor Red
  exit 1
}

Write-Host "Sidecar gerado em: $Exe" -ForegroundColor Green
