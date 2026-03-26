#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

if [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
elif [ -f ".venv/Scripts/activate" ]; then
    source .venv/Scripts/activate
fi

require_tool() {
    local tool_name="$1"
    local install_hint="$2"
    if ! command -v "$tool_name" >/dev/null 2>&1; then
        echo "ERROR: Missing required tool '$tool_name'. $install_hint" >&2
        exit 1
    fi
}

echo "==> Running repository security checks"

require_tool semgrep "Install it with 'pip install -e .[dev]' or 'pip install semgrep'."
require_tool gitleaks "Install it from https://github.com/gitleaks/gitleaks/releases or your package manager."
require_tool trivy "Install it from https://trivy.dev/latest/getting-started/installation/."

echo "[1/6] semgrep"
semgrep --config auto --error --exclude .venv --exclude logs --exclude build --exclude dist --exclude .git --exclude .env --exclude .pytest_cache .

echo "[2/6] gitleaks"
if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    gitleaks protect --staged --redact --verbose
else
    gitleaks detect --source . --no-banner --redact --exit-code 1
fi

echo "[3/6] trivy"
trivy fs --scanners vuln,secret,misconfig --skip-dirs .git --skip-dirs .venv --skip-dirs logs --skip-dirs .pytest_cache --skip-files .env --exit-code 1 --no-progress .

echo "[4/6] bandit"
if command -v bandit >/dev/null 2>&1; then
    bandit -q -r rundeck_mcp
else
    echo "WARNING: bandit not installed; skipping. Install with 'pip install -e .[dev]'." >&2
fi

echo "[5/6] pip-audit"
TMP_REQUIREMENTS="$(mktemp)"
python - <<'PY' > "$TMP_REQUIREMENTS"
from pathlib import Path
import tomllib

pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
for dependency in pyproject["project"]["dependencies"]:
    print(dependency)
PY

if python -c "import pip_audit" >/dev/null 2>&1; then
    python -m pip_audit -r "$TMP_REQUIREMENTS" --ignore-vuln GHSA-5239-wwwm-4pmq
elif command -v pip-audit >/dev/null 2>&1; then
    PIPAPI_PYTHON_LOCATION="$(command -v python)" pip-audit -r "$TMP_REQUIREMENTS" --ignore-vuln GHSA-5239-wwwm-4pmq
else
    echo "WARNING: pip-audit not installed; skipping. Install with 'pip install -e .[dev]'." >&2
fi
rm -f "$TMP_REQUIREMENTS"

echo "[6/6] pytest"
pytest tests/ -v

echo "==> Security checks completed successfully"
