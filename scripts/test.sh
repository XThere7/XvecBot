#!/usr/bin/env bash
# scripts/test.sh — run all backend tests
set -euo pipefail
cd backend
source .venv/bin/activate 2>/dev/null || true
export PYTHONPATH=.
pytest app/tests/ -v --tb=short "$@"
