# ITA-Maskit Windows build script (PyInstaller)
# Run from the project root:
#   powershell -ExecutionPolicy Bypass -File scripts/build_windows.ps1 -Variant python
#   powershell -ExecutionPolicy Bypass -File scripts/build_windows.ps1 -Variant native
# Output:
#   python -> dist\ITA-Maskit.exe
#   native -> dist\ITA-Maskit-native.exe
#
# Prerequisite: Python 3.10+ installed (with pip). This script installs all deps.
# Native variant also needs CMake + MSVC.
#
# NOTE: keep this file pure ASCII (no Chinese chars). Windows PowerShell 5.1
# reads .ps1 without UTF-8 BOM as GBK/ANSI, so non-ASCII breaks parsing.

param(
    [ValidateSet("python", "native")]
    [string]$Variant = "python"
)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

# Pick Python: prefer the `py` launcher, fall back to `python`.
# Do NOT do $py=@("py","-3") then & $py -- PowerShell treats the array as a
# single command name and fails. Use a function with literal name + @args.
if (Get-Command py -ErrorAction SilentlyContinue) {
    function Invoke-Py { & py -3 @args }
    Write-Host "Using Python: py -3"
} else {
    function Invoke-Py { & python @args }
    Write-Host "Using Python: python"
}

Write-Host "=== Upgrade pip ==="
Invoke-Py -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw "pip upgrade failed" }

Write-Host "=== Install project deps (CLI + GUI + image + LLM + pdf) ==="
Invoke-Py -m pip install -e ".[gui,image,llm,pdf]"
if ($LASTEXITCODE -ne 0) { throw "dependency install failed" }

Write-Host "=== Install PyInstaller ==="
Invoke-Py -m pip install pyinstaller
if ($LASTEXITCODE -ne 0) { throw "PyInstaller install failed" }

if ($Variant -eq "native") {
    Write-Host "=== Native core (required for -Variant native) ==="
    Invoke-Py -m pip install pybind11
    if ($LASTEXITCODE -ne 0) { throw "pip install pybind11 failed" }
    & powershell -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "build_native.ps1")
    if ($LASTEXITCODE -ne 0) { throw "native build failed" }
    $env:MASKIT_EXE_NAME = "ITA-Maskit-native"
    $env:MASKIT_BUNDLE_NATIVE = "1"
} else {
    Write-Host "=== Python variant: skip native core ==="
    $env:MASKIT_EXE_NAME = "ITA-Maskit"
    $env:MASKIT_BUNDLE_NATIVE = "0"
}

$exeName = $env:MASKIT_EXE_NAME
Write-Host "=== Build (ITA-Maskit.spec -> $exeName.exe) ==="
Invoke-Py -m PyInstaller ITA-Maskit.spec --clean --noconfirm
if ($LASTEXITCODE -ne 0) { throw "build failed" }

Write-Host ""
Write-Host "=== Done ==="
Write-Host "Variant: $Variant"
Write-Host "Executable: $PWD\dist\$exeName.exe (double-click to run)"
Write-Host "Notes:"
Write-Host "  1. Image masking (beta) needs tesseract OCR installed separately"
Write-Host "  2. AI rule generation needs MASKIT_LLM_API_KEY env var"
Write-Host "  3. Or grab a prebuilt exe from GitHub Actions artifacts"
