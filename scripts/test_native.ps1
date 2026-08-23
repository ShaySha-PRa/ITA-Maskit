# Native import + Python parity smoke (Windows).
# NOTE: keep this file ASCII-only for Windows PowerShell 5.1.

$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

function Resolve-PythonExe {
    if ($env:pythonLocation) {
        $candidate = Join-Path $env:pythonLocation "python.exe"
        if (Test-Path $candidate) { return $candidate }
    }
    $cmd = Get-Command python -ErrorAction SilentlyContinue
    if ($cmd -and $cmd.Source) { return $cmd.Source }
    if (Get-Command py -ErrorAction SilentlyContinue) {
        $out = & py -3 -c "import sys; print(sys.executable)"
        if ($LASTEXITCODE -eq 0 -and $out) {
            return ([string]$out).Trim()
        }
    }
    throw "Python executable not found (set pythonLocation or put python on PATH)"
}

$PyExe = Resolve-PythonExe
function Invoke-Py { & $script:PyExe @args }
Write-Host "Python: $PyExe"

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
