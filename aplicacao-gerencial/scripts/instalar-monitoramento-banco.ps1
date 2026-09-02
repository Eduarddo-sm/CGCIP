param(
    [int]$IntervaloMinutos = 5
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path (Split-Path -Parent $ProjectRoot) "aplicacao-negocial\.venv\Scripts\pythonw.exe"
$Script = Join-Path $PSScriptRoot "database_watchdog.py"
$TaskName = "Projeto Negocial - Watchdog PostgreSQL"

if (-not (Test-Path -LiteralPath $Python)) {
    throw "Runtime Python nao encontrado: $Python"
}

$Action = New-ScheduledTaskAction -Execute $Python -Argument "`"$Script`"" -WorkingDirectory $ProjectRoot
$Trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) `
    -RepetitionInterval (New-TimeSpan -Minutes $IntervaloMinutos) `
    -RepetitionDuration (New-TimeSpan -Days 3650)
$Settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew

Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings `
    -Description "Valida heartbeat, pool e alertas operacionais do PostgreSQL." -Force | Out-Null

Write-Host "Monitoramento instalado: $TaskName (a cada $IntervaloMinutos minuto(s))."
