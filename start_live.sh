#!/usr/bin/env bash
# Uruchamia live.py (waga swin) — recznie i po zalogowaniu do pulpitu
# (~/.config/autostart/pigweight-live.desktop, instaluje install_autostart.sh).
#
# live.py dziala w petli: gdy padnie (np. Segmentation fault w depthai po
# awarii OAK-D), uruchamia sie ponownie po RESTART_DELAY_S. Wyjscie klawiszem Q
# (kod 0) konczy petle.
#
# Jesli live.py: "No available devices" / "Insufficient permissions",
# a lsusb widzi Movidius (03e7) — zainstaluj udev:
#   ./check/install_oak_udev.sh
# potem odlacz/podlacz OAK-D.
set -uo pipefail

RESTART_DELAY_S=5
NET_WAIT_S=60

# Cale cialo w funkcji: bash parsuje ja w calosci przed startem, wiec
# git pull, ktory podmieni ten plik, nie psuje dzialajacego skryptu.
main() {
  local ROOT
  ROOT="$(cd "$(dirname "$0")" && pwd)"
  cd "$ROOT" || exit 1

  # Tylko jedna instancja (autostart + reczne uruchomienie)
  exec 9>"/tmp/pigweight-live-$(id -u).lock"
  if ! flock -n 9; then
    echo "start_live: live.py juz dziala (blokada /tmp/pigweight-live-$(id -u).lock)"
    exit 0
  fi

  local LOG="$ROOT/live_autostart.log"
  exec >>"$LOG" 2>&1
  echo "======== $(date -Iseconds) start_live ========"
  echo "ROOT=$ROOT USER=$(id -un) HOME=${HOME:-?} DISPLAY=${DISPLAY:-?}"

  git_pull "$ROOT"

  # Virtualenv projektu (jesli istnieje)
  local PYTHON
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
  export QT_QPA_PLATFORM="${QT_QPA_PLATFORM:-xcb}"

  # Po boocie daj czas na USB (OAK-D) i pulpit — tylko tuz po starcie systemu
  local UPTIME_S
  UPTIME_S="$(awk '{print int($1)}' /proc/uptime 2>/dev/null || echo 0)"
  if [[ "${PIGWEIGHT_BOOT_DELAY:-}" == "1" && "$UPTIME_S" -lt 180 ]]; then
    echo ">>> start_live: czekam 20 s na USB/DISPLAY..."
    sleep 20
  fi

  if [[ ! -f "$ROOT/models/pig_seg_best.pt" ]]; then
    echo ">>> start_live: UWAGA — brak $ROOT/models/pig_seg_best.pt (wazenie po S / spuscie padnie)"
  fi

  local CHILD="" RC restarts=0
  trap 'echo ">>> start_live: stop"; [[ -n "$CHILD" ]] && kill "$CHILD" 2>/dev/null; exit 0' TERM INT HUP

  while true; do
    wait_for_oak "$ROOT"
    echo ">>> start_live: $(date -Iseconds) $PYTHON $ROOT/live.py (restart #$restarts)"
    "$PYTHON" -u "$ROOT/live.py" &
    CHILD=$!
    wait "$CHILD"
    RC=$?
    CHILD=""
    if [[ "$RC" -eq 0 ]]; then
      echo ">>> start_live: live.py zakonczony (Q) — koniec"
      exit 0
    fi
    restarts=$((restarts + 1))
    echo ">>> start_live: $(date -Iseconds) live.py padl (kod $RC$([[ $RC -gt 128 ]] && echo ", sygnal $((RC - 128))")) — restart za ${RESTART_DELAY_S} s"
    sleep "$RESTART_DELAY_S"
  done
}

# Aktualizacja kodu z GitHuba — czeka na siec (DNS), brak sieci nie blokuje startu
git_pull() {
  local ROOT="$1"
  if ! command -v git >/dev/null || ! git -C "$ROOT" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    echo ">>> start_live: brak repo git w $ROOT — pomijam pull"
    return
  fi
  local i
  for ((i = 0; i < NET_WAIT_S; i += 3)); do
    getent hosts github.com >/dev/null 2>&1 && break
    sleep 3
  done
  echo ">>> start_live: git pull..."
  local OLD_HEAD
  OLD_HEAD="$(git -C "$ROOT" rev-parse HEAD 2>/dev/null || true)"
  if git -C "$ROOT" pull --ff-only 2>&1; then
    echo ">>> start_live: git pull OK ($(git -C "$ROOT" log --oneline -1))"
    # Nowa wersja przyciski.py -> restart uslugi przyciskow (systemctl --user)
    if [[ -n "$OLD_HEAD" ]] && git -C "$ROOT" diff --name-only "$OLD_HEAD" HEAD | grep -qx 'przyciski.py'; then
      echo ">>> start_live: zmieniony przyciski.py — restart uslugi przyciski"
      XDG_RUNTIME_DIR="/run/user/$(id -u)" systemctl --user restart przyciski 2>&1 \
        || echo ">>> start_live: UWAGA — restart przyciski nieudany"
    fi
  else
    echo ">>> start_live: UWAGA — git pull nieudany, startuje lokalna wersja"
  fi
}

# Czeka az OAK-D pojawi sie w USB (po boocie i po awarii kamery bywa pozno)
wait_for_oak() {
  local ROOT="$1" i
  for i in $(seq 1 40); do
    if lsusb 2>/dev/null | grep -qiE 'Luxonis|Movidius|03e7'; then
      return
    fi
    echo ">>> start_live: brak OAK-D w USB (proba $i/40), czekam 3s..."
    sleep 3
  done
  echo ">>> start_live: UWAGA — brak 03e7 w lsusb (kabel/zasilanie?)"
  if [[ ! -f /etc/udev/rules.d/80-movidius.rules ]]; then
    echo ">>> start_live: UWAGA — brak /etc/udev/rules.d/80-movidius.rules — uruchom: $ROOT/check/install_oak_udev.sh"
  fi
}

main "$@"
