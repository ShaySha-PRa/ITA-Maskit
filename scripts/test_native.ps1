# Native import + Python parity smoke (Windows).
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

if (Get-Command py -ErrorAction SilentlyContinue) {
    function Invoke-Py { & py -3 @args }
} else {
    function Invoke-Py { & python @args }
}

Invoke-Py -c "import maskit._native as n; print(n.native_version())"
if ($LASTEXITCODE -ne 0) { throw "maskit._native import failed" }

$env:MASKIT_NATIVE = "compare"
Invoke-Py -m pytest tests/test_native_parity.py tests/test_hmac_v2.py -q
if ($LASTEXITCODE -ne 0) { throw "native parity pytest failed" }
