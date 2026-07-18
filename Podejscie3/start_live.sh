#!/usr/bin/env bash
# Uruchamia live.py (waga swin) — recznie i po boocie (systemd / autostart GUI).
#
# Jesli live.py: "No available devices" / "Insufficient permissions",
# a lsusb widzi Movidius (03e7) — zainstaluj udev:
#   ./check/install_oak_udev.sh
# potem odlacz/podlacz OAK-D.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

LOG="$ROOT/live_autostart.log"
exec >>"$LOG" 2>&1
echo "======== $(date -Iseconds) start_live ========"
echo "ROOT=$ROOT USER=$(id -un) HOME=${HOME:-?} DISPLAY=${DISPLAY:-?}"

# Virtualenv projektu (jesli istnieje)
if [[ -x "$ROOT/.venv/bin/python" ]]; then
  PYTHON="$ROOT/.venv/bin/python"
elif [[ -x "$ROOT/venv/bin/python" ]]; then
  PYTHON="$ROOT/venv/bin/python"
else
  PYTHON="$(command -v python3 || true)"
fi

if [[ -z "${PYTHON}" || ! -x "${PYTHON}" ]]; then
  echo "BLAD: brak python3 / .venv — zainstaluj venv w $ROOT"
  exit 1
fi

if [[ ! -f "$ROOT/live.py" ]]; then
  echo "BLAD: brak live.py w $ROOT"
  exit 1
fi

export DISPLAY="${DISPLAY:-:0}"
if [[ -f "${HOME:-}/.Xauthority" ]]; then
  export XAUTHORITY="${XAUTHORITY:-$HOME/.Xauthority}"
fi

# Po boocie daj czas na USB (OAK-D), SPI i pulpit
if [[ "${PIGWEIGHT_BOOT_DELAY:-}" == "1" ]]; then
  echo ">>> start_live: czekam 20 s na USB/DISPLAY..."
  sleep 20
  echo ">>> start_live: czekam na OAK-D w lsusb..."
  for i in $(seq 1 40); do
    if lsusb 2>/dev/null | grep -qiE 'Luxonis|Movidius|03e7'; then
      echo ">>> start_live: OAK-D widoczna w USB (proba $i)"
      break
    fi
    echo ">>> start_live: brak OAK-D w USB (proba $i/40), czekam 3s..."
    sleep 3
  done
  if ! lsusb 2>/dev/null | grep -qiE '03e7|Movidius'; then
    echo ">>> start_live: UWAGA — brak 03e7 w lsusb (kabel/zasilanie?)"
  elif [[ ! -f /etc/udev/rules.d/80-movidius.rules ]]; then
    echo ">>> start_live: UWAGA — brak /etc/udev/rules.d/80-movidius.rules"
    echo ">>>             uruchom: $ROOT/check/install_oak_udev.sh"
  fi
fi

echo ">>> start_live: $PYTHON $ROOT/live.py"
exec "$PYTHON" -u "$ROOT/live.py"
