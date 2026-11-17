#!/usr/bin/env bash
# Local mirror of .github/workflows/test.yml. Fails if any test is skipped, because a skip
# here means the venv cannot import Hermes and the 60 native-platform tests did not run.
# Usage: scripts/check.sh [python]   (default: $PYTHON, else python3)
# The venv needs: pip install -e '.[dev]' pillow ruamel.yaml, and PYTHONPATH pointing at a Hermes checkout.
set -euo pipefail
cd "$(dirname "$0")/.."
PY="${1:-${PYTHON:-python3}}"
export PYTHONPATH="${HERMES_SRC:-$HOME/.hermes/hermes-agent}:$PWD${PYTHONPATH:+:$PYTHONPATH}"
"$PY" -m ruff check hermes_lark_streaming tests scripts __init__.py
"$PY" -m mypy hermes_lark_streaming scripts
out=$("$PY" -m pytest tests -q -p no:cacheprovider -rs 2>&1) || { echo "$out" | tail -30; exit 1; }
echo "$out" | tail -1
if echo "$out" | grep -qE '[0-9]+ skipped'; then
  echo "$out" | grep -E '^SKIPPED' >&2
  echo "FAIL: tests were skipped (see above). Fix the venv; skips hide the native-platform tests." >&2
  exit 1
fi
