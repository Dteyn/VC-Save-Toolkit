#!/usr/bin/env sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$SCRIPT_DIR"

echo "VC Save Toolkit - Linux dependency installer"

if command -v python3 >/dev/null 2>&1; then
    PYTHON=python3
elif command -v python >/dev/null 2>&1; then
    PYTHON=python
else
    echo "ERROR: Python 3.10 or newer was not found in PATH." >&2
    exit 1
fi

if ! "$PYTHON" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)'; then
    echo "ERROR: VC Save Toolkit requires Python 3.10 or newer." >&2
    "$PYTHON" --version >&2
    exit 1
fi

echo "Using: $($PYTHON --version 2>&1)"
"$PYTHON" -m pip install -r "$SCRIPT_DIR/requirements.txt"

echo
echo "Dependencies installed successfully."
echo "Launch with: $PYTHON vc_save_toolkit.pyw"
