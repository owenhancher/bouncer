#!/usr/bin/env bash
# One-command launcher for Bouncer
set -euo pipefail
cd "$(dirname "$0")"
[ -d .venv ] || python3 -m venv .venv
.venv/bin/pip install -q -r requirements.txt
exec .venv/bin/streamlit run app.py "$@"
