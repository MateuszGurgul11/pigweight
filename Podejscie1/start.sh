#!/usr/bin/env bash
# Uruchamia backend (uvicorn :8000) i frontend (Vite dev) w jednym terminalu.
# Git Bash / WSL / Linux / macOS:
#   chmod +x start-all.sh && ./start-all.sh
# Zatrzymanie: Ctrl+C (backend zostanie ubity przez trap).

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

pick_python() {
  [[ -x "$ROOT/venv/bin/python" ]] && { echo "$ROOT/venv/bin/python"; return 0; }
  [[ -x "$ROOT/venv/Scripts/python.exe" ]] && { echo "$ROOT/venv/Scripts/python.exe"; return 0; }
  [[ -x "$ROOT/.venv/bin/python" ]] && { echo "$ROOT/.venv/bin/python"; return 0; }
  [[ -x "$ROOT/.venv/Scripts/python.exe" ]] && { echo "$ROOT/.venv/Scripts/python.exe"; return 0; }
  command -v python3 &>/dev/null && { echo python3; return 0; }
  command -v python &>/dev/null && { echo python; return 0; }
  echo "Brak Pythona (venv lub PATH). Utwórz venv w katalogu projektu lub zainstaluj Python." >&2
  return 1
}

PYTHON="$(pick_python)" || exit 1

BACKEND_PID=""
cleanup() {
  if [[ -n "${BACKEND_PID}" ]] && kill -0 "${BACKEND_PID}" 2>/dev/null; then
    kill "${BACKEND_PID}" 2>/dev/null || true
    wait "${BACKEND_PID}" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

echo "[start-all] Backend: http://0.0.0.0:8000  (health: http://localhost:8000/healthz)"
(
  cd "$ROOT/backend"
  exec "$PYTHON" -m uvicorn app.main:app --host 0.0.0.0 --port 8000
) &
BACKEND_PID=$!

# Krótka pauza, żeby port 8000 zdążył wstać zanim poleci pierwszy request z Vite.
sleep 2

echo "[start-all] Frontend (Vite): dev-server w terminalu poniżej"
cd "$ROOT/web"
if [[ ! -d node_modules ]]; then
  echo "[start-all] Brak web/node_modules — uruchamiam npm install..."
  npm install
fi
npm run dev
