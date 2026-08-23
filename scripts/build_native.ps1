# Build the native extension with MSVC + CMake.
# Requires: Visual Studio Build Tools, CMake, Python 3.10+.
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

if (Get-Command py -ErrorAction SilentlyContinue) {
    function Invoke-Py { & py -3 @args }
} else {
    function Invoke-Py { & python @args }
}

$build = Join-Path $PWD "native\build"
New-Item -ItemType Directory -Force -Path $build | Out-Null

$py = (Invoke-Py -c "import sys; print(sys.executable)").Trim()
cmake -S native -B $build -DPython_EXECUTABLE=$py
if ($LASTEXITCODE -ne 0) { throw "cmake configure failed" }

cmake --build $build --config Release
if ($LASTEXITCODE -ne 0) { throw "cmake build failed" }

ctest --test-dir $build -C Release --output-on-failure
if ($LASTEXITCODE -ne 0) { throw "ctest failed" }

Invoke-Py -c "import maskit._native as n; print('import ok', n.native_version(), n.build_compiler())"
if ($LASTEXITCODE -ne 0) { throw "python import of maskit._native failed" }
