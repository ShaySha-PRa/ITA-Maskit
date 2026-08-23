#!/usr/bin/env bash
# Install ITA-Maskit as the Python or Native variant.
#   bash scripts/install.sh python
#   bash scripts/install.sh native
# Optional extras (comma-separated): gui,image,llm,pdf,dev
#   bash scripts/install.sh python gui,pdf
#   bash scripts/install.sh native gui,image,llm,pdf
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

VARIANT="${1:-}"
EXTRAS="${2:-}"

usage() {
  echo "Usage: bash scripts/install.sh {python|native} [extras]" >&2
  echo "  extras: comma-separated pip extras, e.g. gui,image,llm,pdf" >&2
  exit 2
}

case "$VARIANT" in
  python|native) ;;
  *) usage ;;
esac

PY="${PYTHON:-python3}"
if ! command -v "$PY" >/dev/null 2>&1; then
  echo "python3 not found (set PYTHON=...)" >&2
  exit 1
fi

parts=()
if [ "$VARIANT" = "native" ]; then
  parts+=(native)
fi
if [ -n "$EXTRAS" ]; then
  IFS=',' read -r -a extra_parts <<< "$EXTRAS"
  parts+=("${extra_parts[@]}")
fi

if [ "${#parts[@]}" -eq 0 ]; then
  spec="."
else
  joined=$(IFS=','; echo "${parts[*]}")
  spec=".[${joined}]"
fi

echo "=== pip install -e ${spec} ==="
"$PY" -m pip install -e "$spec"

if [ "$VARIANT" = "native" ]; then
  echo "=== build native core ==="
  bash "$ROOT/scripts/build_native.sh"
fi

echo
echo "Installed variant: $VARIANT"
echo "Check with: maskit --version"
