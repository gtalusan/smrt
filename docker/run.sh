#!/bin/sh
# Shim: the tick logic lives in runner.py (same directory).
dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
exec "${PYTHON:-python3}" "$dir/runner.py"
