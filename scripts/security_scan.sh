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

prepend_path_if_dir() {
    local dir_path="$1"
    if [ -d "$dir_path" ] && [[ ":$PATH:" != *":$dir_path:"* ]]; then
        PATH="$dir_path:$PATH"
    fi
}

# Git hooks can run with a reduced PATH (especially when triggered from GUI clients).
# Add common package manager/bin locations so required security tools are discoverable.
prepend_path_if_dir "$HOME/.local/bin"
prepend_path_if_dir "$HOME/.cargo/bin"
prepend_path_if_dir "$HOME/.nvm/versions/node/current/bin"
prepend_path_if_dir "/home/linuxbrew/.linuxbrew/bin"
prepend_path_if_dir "/home/linuxbrew/.linuxbrew/sbin"
prepend_path_if_dir "/opt/homebrew/bin"
prepend_path_if_dir "/opt/homebrew/sbin"
prepend_path_if_dir "/usr/local/bin"
prepend_path_if_dir "/usr/local/sbin"
export PATH

require_tool() {
    local tool_name="$1"
    local install_hint="$2"
    if ! command -v "$tool_name" >/dev/null 2>&1; then
        echo "ERROR: Missing required tool '$tool_name'. $install_hint" >&2
        echo "Current PATH in hook: $PATH" >&2
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
