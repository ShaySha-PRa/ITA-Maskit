# Native import + Python parity smoke (Windows).
# NOTE: keep this file ASCII-only for Windows PowerShell 5.1.

$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

if (Get-Command py -ErrorAction SilentlyContinue) {
    function Invoke-Py { & py -3 @args }
} else {
    function Invoke-Py { & python @args }
}

Write-Host "=== import maskit._native ==="
Invoke-Py -c "import maskit._native as n; print(n.native_version(), n.build_compiler(), n.build_type())"
if ($LASTEXITCODE -ne 0) { throw "maskit._native import failed" }

Write-Host "=== fallback MASKIT_NATIVE=0 ==="
$env:MASKIT_NATIVE = "0"
Invoke-Py -c "from maskit.native import get_backend; b=get_backend(); print(b.name)"
if ($LASTEXITCODE -ne 0) { throw "python fallback failed" }

Write-Host "=== compare parity ==="
$env:MASKIT_NATIVE = "compare"
Invoke-Py -m pytest tests/test_native_parity.py tests/test_native_dictionary.py tests/test_hmac_v2.py tests/test_native_column_pseudo.py -q
if ($LASTEXITCODE -ne 0) { throw "native parity pytest failed" }

Remove-Item Env:MASKIT_NATIVE -ErrorAction SilentlyContinue
Write-Host "Native Windows tests OK"
