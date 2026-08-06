# ITA-Maskit Windows build script (PyInstaller)
# Run from the project root:
#   powershell -ExecutionPolicy Bypass -File scripts/build_windows.ps1
# Output: dist\ITA-Maskit.exe (single file, double-click to run, no Python needed)
#
# Prerequisite: Python 3.10+ installed (with pip). This script installs all deps.
#
# NOTE: keep this file pure ASCII (no Chinese chars). Windows PowerShell 5.1
# reads .ps1 without UTF-8 BOM as GBK/ANSI, so non-ASCII breaks parsing.

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

Write-Host "=== Install project deps (CLI + GUI + image + LLM) ==="
Invoke-Py -m pip install -e ".[gui,image,llm]"
if ($LASTEXITCODE -ne 0) { throw "dependency install failed" }

Write-Host "=== Install PyInstaller ==="
Invoke-Py -m pip install pyinstaller
if ($LASTEXITCODE -ne 0) { throw "PyInstaller install failed" }

Write-Host "=== Build (ITA-Maskit.spec) ==="
Invoke-Py -m PyInstaller ITA-Maskit.spec --clean --noconfirm
if ($LASTEXITCODE -ne 0) { throw "build failed" }

Write-Host ""
Write-Host "=== Done ==="
Write-Host "Executable: $PWD\dist\ITA-Maskit.exe (double-click to run)"
Write-Host "Notes:"
Write-Host "  1. Image masking (beta) needs tesseract OCR installed separately"
Write-Host "  2. AI rule generation needs MASKIT_LLM_API_KEY env var"
Write-Host "  3. Or grab a prebuilt exe from GitHub Actions artifacts"
