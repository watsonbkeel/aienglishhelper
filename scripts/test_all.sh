#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
cd "$ROOT"
python -m compileall -q english_class pi scripts tests
python -m pytest -q
node --test tests_js/*.test.js
find miniprogram -name '*.js' -print0 | xargs -0 -n1 node --check
for script in scripts/*.sh; do bash -n "$script"; done
