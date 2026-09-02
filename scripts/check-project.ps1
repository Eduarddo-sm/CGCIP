param(
    [switch]$E2E
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$gerencial = Join-Path $root "aplicacao-gerencial"
$negocial = Join-Path $root "aplicacao-negocial"
$gerencialPython = Join-Path $gerencial ".venv\Scripts\python.exe"
$negocialPython = Join-Path $negocial ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $gerencialPython)) {
    throw "Python do Gerencial nao encontrado: $gerencialPython"
}
if (-not (Test-Path -LiteralPath $negocialPython)) {
    throw "Python do Negocial nao encontrado: $negocialPython"
}

& (Join-Path $PSScriptRoot "sync-excel-grid.ps1") -Check

try {
    Push-Location $gerencial
    & $gerencialPython -m unittest discover -s tests -p "test_*.py"
    if ($LASTEXITCODE -ne 0) { throw "Testes Python do Gerencial falharam." }
    & node tests\negociador_period.test.mjs
    if ($LASTEXITCODE -ne 0) { throw "Teste JS do Gerencial falhou." }
    Pop-Location

    Push-Location $negocial
    & $negocialPython -m unittest discover -s tests -p "test_*.py"
    if ($LASTEXITCODE -ne 0) { throw "Testes Python do Negocial falharam." }
    & npm.cmd test
    if ($LASTEXITCODE -ne 0) { throw "Testes JS do Negocial falharam." }
    Pop-Location

    if ($E2E) {
        Push-Location $gerencial
        # playwright.config.js already owns testDir; passing a Windows path is
        # interpreted as a regular expression and may produce "No tests found".
        & npx.cmd playwright test
        if ($LASTEXITCODE -ne 0) { throw "Testes E2E falharam." }
        Pop-Location
    }
} finally {
    while ((Get-Location).Path -ne $root) { Pop-Location }
}

Write-Output "Validacao concluida com sucesso."
