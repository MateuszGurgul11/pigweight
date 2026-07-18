#!/usr/bin/env bash
# Uruchamia live.py (waga swin) — uzywane recznie i przez systemd po boocie.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

# Virtualenv projektu (jesli istnieje)
if [[ -x "$ROOT/.venv/bin/python" ]]; then
  PYTHON="$ROOT/.venv/bin/python"
elif [[ -x "$ROOT/venv/bin/python" ]]; then
  PYTHON="$ROOT/venv/bin/python"
else
  PYTHON="$(command -v python3)"
fi

# GUI / OpenCV — potrzebne gdy jest pulpit; na headless i tak dziala ekran ILI9341
export DISPLAY="${DISPLAY:-:0}"
if [[ -f "$HOME/.Xauthority" ]]; then
  export XAUTHORITY="${XAUTHORITY:-$HOME/.Xauthority}"
fi

# Krótka pauza po boocie — USB/OAK-D i SPI potrzebuja chwili
if [[ "${PIGWEIGHT_BOOT_DELAY:-}" == "1" ]]; then
  echo ">>> start_live: czekam 15 s na urzadzenia..."
  sleep 15
fi

echo ">>> start_live: $PYTHON $ROOT/live.py"
exec "$PYTHON" "$ROOT/live.py"
