#!/usr/bin/env bash
# Every check that CI runs. Usage: scripts/test.sh
set -euo pipefail
cd "$(dirname "$0")/.."
PY="${PYTHON:-python3}"

echo "== unit tests"
"$PY" -m unittest discover -s tests -t .

echo "== demo build"
out="$(mktemp -d)/demo.html"
"$PY" -m poker.build examples/demo-cards.json --out "$out"

echo "== template JS syntax"
if command -v node >/dev/null; then
  "$PY" - "$out" > "${out%.html}.js" <<'PYEOF'
import re, sys
print(re.search(r"<script>(.*)</script>", open(sys.argv[1], encoding="utf-8").read(), re.S).group(1))
PYEOF
  node --check "${out%.html}.js"
else
  echo "   node not found — skipped"
fi

echo "== no session data in git"
tracked="$(git ls-files sessions | grep -v '^sessions/.gitkeep$' || true)"
if [ -n "$tracked" ]; then
  echo "people's data is tracked under sessions/:"; echo "$tracked"; exit 1
fi

echo "OK"
