#!/usr/bin/env bash
# scripts/setup.sh — one-command dev environment setup
set -euo pipefail

echo "=== Production RAG — Dev Setup ==="

# 1. Python virtualenv + deps
echo "[1/4] Installing Python dependencies..."
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -q --upgrade pip
pip install -q -r ../requirements.txt
cd ..

# 2. Frontend deps
echo "[2/4] Installing Node dependencies..."
cd frontend
npm install
cd ..

# 3. Copy .env if not present
if [ ! -f .env ]; then
    cp .env.example .env
    echo "[3/4] Created .env from .env.example — set API_KEY and OPENROUTER_API_KEY."
else
    echo "[3/4] .env already exists, skipping."
fi

# 4. Create data directories
mkdir -p data/uploads data/processed data/embeddings
echo "[4/4] Data directories ready."

echo ""
echo "Setup complete! LLM is OpenRouter (cloud API — no local model needed):"
echo "  1. Get a key at https://openrouter.ai/keys and set OPENROUTER_API_KEY in .env"
echo "  Backend:  cd backend && source .venv/bin/activate && uvicorn app.main:app --reload"
echo "  Frontend: cd frontend && npm run dev"
