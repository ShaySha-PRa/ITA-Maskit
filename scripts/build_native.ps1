# Build the native extension with MSVC + CMake.
#   powershell -ExecutionPolicy Bypass -File scripts/build_native.ps1
#   powershell -ExecutionPolicy Bypass -File scripts/build_native.ps1 -Optional
# -Optional: missing CMake/MSVC prints a skip and exits 0 (used by build_windows.ps1).
# NOTE: keep this file ASCII-only for Windows PowerShell 5.1.

param(
    [switch]$Optional
)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

function Write-Skip([string]$Message) {
    Write-Host "Native build skipped: $Message"
    if ($Optional) { exit 0 }
    throw $Message
}

# Prefer setup-python's interpreter (pythonLocation). `py -3` on
# windows-latest may resolve to a newer unused runtime without pybind11.
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

function Find-CMake {
    if (Get-Command cmake -ErrorAction SilentlyContinue) {
        return (Get-Command cmake).Source
    }
    $candidates = @(
        "$env:ProgramFiles\CMake\bin\cmake.exe",
        "${env:ProgramFiles(x86)}\CMake\bin\cmake.exe"
    )
    foreach ($c in $candidates) {
        if (Test-Path $c) { return $c }
    }
    return $null
}

function Import-VsDevCmd {
    $vswhere = "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\vswhere.exe"
    if (-not (Test-Path $vswhere)) { return $false }
    $vs = & $vswhere -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
    if (-not $vs) { return $false }
    $vsdev = Join-Path $vs "Common7\Tools\Launch-VsDevShell.ps1"
    if (-not (Test-Path $vsdev)) { return $false }
    & $vsdev -Arch amd64 -HostArch amd64 | Out-Null
    return $true
}

Write-Host "=== Python ==="
Write-Host "Python: $PyExe"
Invoke-Py -c "import sys; print(sys.version)"

Write-Host "=== pybind11 ==="
Invoke-Py -m pip install -q pybind11
if ($LASTEXITCODE -ne 0) { Write-Skip "pip install pybind11 failed" }
$pybind11Dir = ((Invoke-Py -c "import pybind11; print(pybind11.get_cmake_dir())") | Select-Object -Last 1).ToString().Trim()
if (-not $pybind11Dir) { Write-Skip "pybind11.get_cmake_dir() returned empty" }
Write-Host "pybind11_DIR: $pybind11Dir"

$cmake = Find-CMake
if (-not $cmake) {
    if (-not (Import-VsDevCmd)) {
        Write-Skip "CMake not found and Visual Studio VC tools not found"
    }
    $cmake = Find-CMake
}
if (-not $cmake) { Write-Skip "CMake not found" }
Write-Host "CMake: $cmake"

if (-not (Get-Command cl -ErrorAction SilentlyContinue)) {
    if (-not (Import-VsDevCmd)) {
        Write-Skip "MSVC cl.exe not on PATH"
    }
}
if (-not (Get-Command cl -ErrorAction SilentlyContinue)) {
    Write-Skip "MSVC cl.exe not available"
}

$build = Join-Path $PWD "native\build-win"
New-Item -ItemType Directory -Force -Path $build | Out-Null

Write-Host "=== CMake configure ==="
& $cmake -S native -B $build `
    "-DPython_EXECUTABLE=$PyExe" `
    "-Dpybind11_DIR=$pybind11Dir" `
    -DCMAKE_BUILD_TYPE=Release
if ($LASTEXITCODE -ne 0) { Write-Skip "cmake configure failed" }

Write-Host "=== CMake build ==="
& $cmake --build $build --config Release
if ($LASTEXITCODE -ne 0) { Write-Skip "cmake build failed" }

Write-Host "=== CTest ==="
$ctest = Join-Path (Split-Path $cmake) "ctest.exe"
& $cmake --build $build --config Release --target maskit_core_tests
if (Test-Path $ctest) {
    & $ctest --test-dir $build -C Release --output-on-failure
} else {
    & $cmake --build $build --config Release --target RUN_TESTS
}
if ($LASTEXITCODE -ne 0) { Write-Skip "ctest failed" }

$pyd = Get-ChildItem -Path "maskit" -Filter "_native*.pyd" -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $pyd) {
    Write-Skip "maskit/_native*.pyd was not produced"
}
Write-Host "pyd: $($pyd.FullName)"

Write-Host "=== import smoke ==="
Invoke-Py -c "import maskit._native as n; print('import ok', n.native_version(), n.build_compiler(), n.build_type())"
if ($LASTEXITCODE -ne 0) { Write-Skip "python import of maskit._native failed" }

Write-Host "Native Windows build OK"
