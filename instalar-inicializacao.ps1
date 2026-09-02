$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Launcher = Join-Path $Root "iniciar-sistemas.ps1"
$TaskName = "Projeto Negocial - Servidores"

if (-not (Test-Path -LiteralPath $Launcher)) {
  throw "Inicializador nao encontrado: $Launcher"
}

$action = New-ScheduledTaskAction `
  -Execute "powershell.exe" `
  -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$Launcher`""
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$settings = New-ScheduledTaskSettingsSet `
  -AllowStartIfOnBatteries `
  -DontStopIfGoingOnBatteries `
  -ExecutionTimeLimit (New-TimeSpan -Days 3650) `
  -RestartCount 3 `
  -RestartInterval (New-TimeSpan -Minutes 1)

Register-ScheduledTask `
  -TaskName $TaskName `
  -Action $action `
  -Trigger $trigger `
  -Settings $settings `
  -Description "Inicia os sistemas Gerencial e Negocial no login do servidor." `
  -Force | Out-Null

Write-Host "Tarefa '$TaskName' instalada com sucesso." -ForegroundColor Green
Write-Host "Ela iniciara os dois sistemas no proximo login deste usuario."
