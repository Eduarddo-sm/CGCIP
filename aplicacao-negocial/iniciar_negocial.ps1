$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = Join-Path $root ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $python)) {
  throw "Ambiente virtual nao encontrado. Crie o .venv e instale requirements.txt antes de iniciar."
}

Set-Location $root
& $python -m uvicorn backend.main:app --host 0.0.0.0 --port 8890
