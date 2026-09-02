param(
    [switch]$Check
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$source = Join-Path $root "shared\frontend\excelGrid.js"
$targets = @(
    (Join-Path $root "aplicacao-gerencial\ui\features\excelGrid.js"),
    (Join-Path $root "aplicacao-negocial\frontend\static\js\excelGrid.js")
)

if (-not (Test-Path -LiteralPath $source)) {
    throw "Fonte compartilhada nao encontrada: $source"
}

$sourceHash = (Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash
$outdated = @()
foreach ($target in $targets) {
    $targetHash = if (Test-Path -LiteralPath $target) {
        (Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash
    } else {
        ""
    }
    if ($targetHash -ne $sourceHash) {
        $outdated += $target
        if (-not $Check) {
            Copy-Item -LiteralPath $source -Destination $target -Force
        }
    }
}

if ($Check -and $outdated.Count -gt 0) {
    $joined = $outdated -join [Environment]::NewLine
    throw "Excel Grid fora de sincronia:`n$joined"
}

if ($Check) {
    Write-Output "Excel Grid sincronizado ($sourceHash)."
} else {
    Write-Output "Excel Grid atualizado em $($targets.Count) aplicacoes."
}
