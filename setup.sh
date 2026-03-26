#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== Rundeck MCP Setup ==="

PYTHON=""
for candidate in python3 python; do
    if command -v "$candidate" >/dev/null 2>&1; then
        version="$($candidate --version 2>&1 | grep -oE '[0-9]+\.[0-9]+' | head -1)"
        major="$(echo "$version" | cut -d. -f1)"
        minor="$(echo "$version" | cut -d. -f2)"
        if [ "$major" -ge 3 ] && [ "$minor" -ge 11 ]; then
            PYTHON="$candidate"
            break
        fi
    fi
done

if [ -z "$PYTHON" ]; then
    echo "ERROR: Python 3.11+ is required but not found."
    exit 1
fi

echo "Using Python: $PYTHON ($($PYTHON --version))"

if [ ! -d ".venv" ]; then
    echo "Creating virtual environment in .venv ..."
    "$PYTHON" -m venv .venv
else
    echo "Virtual environment .venv already exists"
fi

if [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
elif [ -f ".venv/Scripts/activate" ]; then
    source .venv/Scripts/activate
else
    echo "ERROR: Could not find venv activation script"
    exit 1
fi

echo "Installing dependencies ..."
pip install --upgrade pip --quiet
if [ "${INSTALL_DEV_TOOLS:-1}" = "1" ]; then
    pip install -e ".[dev]" --quiet
else
    pip install -e . --quiet
fi

if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    git config core.hooksPath .githooks
fi

chmod +x .githooks/pre-commit .githooks/pre-push scripts/security_scan.sh

echo ""
echo "=== Setup Complete ==="
echo ""
echo "To run the server:"
echo "  .venv/bin/python -m rundeck_mcp.server"
echo ""
echo "Security hooks enabled via .githooks/pre-commit and .githooks/pre-push"
