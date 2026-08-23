#!/bin/bash
set -eu
cd /home/joshua/projects/ITA-maskit-wt-native-core
export PYTHONPATH=/home/joshua/projects/ITA-maskit-wt-native-core

echo "=== C++ smoke / ctest ==="
ctest --test-dir native/build --output-on-failure

echo "=== import maskit._native ==="
python3 - <<'PY'
import maskit._native as n
print("native_version", n.native_version())
print("core_abi_version", n.core_abi_version())
print("detector_version", n.detector_version())
print("schemes", list(n.pseudonym_scheme_versions()))
print("compiler", n.build_compiler())
print("build_type", n.build_type())
print("hash_v1", n.hash_v1("13800138000", "maskit-test-pepper-not-production", 8))
PY

echo "=== fallback MASKIT_NATIVE=0 ==="
MASKIT_NATIVE=0 python3 - <<'PY'
from maskit.native import get_backend
be = get_backend()
print("backend", be.name, be.hash_v1("13800138000", "maskit-test-pepper-not-production", 8))
PY

echo "=== native compare pytest ==="
python3 -m pytest tests/test_native_parity.py tests/test_hmac_v2.py --native-mode=compare -q

echo "=== python backend pytest smoke ==="
python3 -m pytest tests/test_hmac_v2.py tests/test_hmac_collision.py tests/test_benchmark.py --native-mode=python -q

echo "SMOKE OK"
