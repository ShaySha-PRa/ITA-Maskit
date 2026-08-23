#!/bin/bash
set -eu
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BUILD="$ROOT/native/build"
mkdir -p "$BUILD"
cmake -S "$ROOT/native" -B "$BUILD" \
  -DCMAKE_BUILD_TYPE=Release \
  -DPython_EXECUTABLE="$(command -v python3)"
cmake --build "$BUILD" --config Release -j"$(nproc)"
cmake --build "$BUILD" --target maskit_core_tests maskit_core_smoke --config Release
ctest --test-dir "$BUILD" --output-on-failure
python3 -c "import maskit._native as n; print('import ok', n.native_version(), n.build_compiler())"
