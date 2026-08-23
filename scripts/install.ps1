# Install ITA-Maskit as the Python or Native variant.
#   powershell -ExecutionPolicy Bypass -File scripts/install.ps1 -Variant python
#   powershell -ExecutionPolicy Bypass -File scripts/install.ps1 -Variant native
# Optional extras (comma-separated): gui,image,llm,pdf,dev
#   powershell -ExecutionPolicy Bypass -File scripts/install.ps1 -Variant python -Extras gui,pdf
#
# NOTE: keep this file ASCII-only for Windows PowerShell 5.1.

param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("python", "native")]
    [string]$Variant,
    [string]$Extras = ""
)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

if (Get-Command py -ErrorAction SilentlyContinue) {
    function Invoke-Py { & py -3 @args }
    Write-Host "Using Python: py -3"
} else {
    function Invoke-Py { & python @args }
    Write-Host "Using Python: python"
}

$parts = @()
if ($Variant -eq "native") {
    $parts += "native"
}
if ($Extras) {
    $parts += ($Extras -split "," | ForEach-Object { $_.Trim() } | Where-Object { $_ })
}

if ($parts.Count -eq 0) {
    $spec = "."
} else {
    $spec = ".[$($parts -join ',')]"
}

Write-Host "=== pip install -e $spec ==="
Invoke-Py -m pip install -e $spec
if ($LASTEXITCODE -ne 0) { throw "pip install failed" }

if ($Variant -eq "native") {
    Write-Host "=== build native core ==="
    & powershell -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "build_native.ps1")
    if ($LASTEXITCODE -ne 0) { throw "native build failed" }
}

Write-Host ""
Write-Host "Installed variant: $Variant"
Write-Host "Check with: maskit --version"
