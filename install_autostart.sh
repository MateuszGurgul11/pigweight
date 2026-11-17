#!/usr/bin/env bash
# Instaluje autostart live.py po zalogowaniu do pulpitu Raspberry Pi
# (~/.config/autostart/pigweight-live.desktop -> start_live.sh).
#
# start_live.sh sam pilnuje live.py: po awarii (np. Segmentation fault
# w depthai po zawieszeniu OAK-D) uruchamia go ponownie po 5 s.
#
# Uruchom Z folderu projektu (tam gdzie jest live.py), np.:
#   cd ~/Desktop/pigweight
#   ./install_autostart.sh
#   sudo reboot
#
# Logi:     tail -f ~/Desktop/pigweight/live_autostart.log
# Stop:     pkill -f start_live.sh; pkill -f 'python.*live.py'
# Start:    nohup ./start_live.sh >/dev/null 2>&1 &   (z sesji pulpitu)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
USER_NAME="$(id -un)"

# getent bywa niedostepny (np. macOS) — nie wywalaj skryptu przez set -e
HOME_DIR="${HOME:-}"
if command -v getent >/dev/null 2>&1; then
  HOME_DIR="$(getent passwd "$USER_NAME" 2>/dev/null | cut -d: -f6 || true)"
fi
HOME_DIR="${HOME_DIR:-$HOME}"
HOME_DIR="${HOME_DIR:-/home/$USER_NAME}"

echo "=========================================="
echo "  PigWeight — instalacja autostartu"
echo "=========================================="
echo "Folder projektu:"
echo "  $ROOT"
echo "Uzytkownik: $USER_NAME"
echo "HOME:       $HOME_DIR"
echo

if [[ ! -f "$ROOT/live.py" ]]; then
  echo "BLAD: w $ROOT nie ma live.py"
  echo "      Uruchom:  cd ~/Desktop/pigweight && ./install_autostart.sh"
  exit 1
fi
if [[ ! -x "$ROOT/.venv/bin/python" && ! -x "$ROOT/venv/bin/python" ]]; then
  echo "UWAGA: brak .venv w $ROOT — autostart moze uzyc systemowego python3"
fi
if [[ ! -f "$ROOT/models/pig_seg_best.pt" ]]; then
  echo "UWAGA: brak models/pig_seg_best.pt — wazenie padnie po S / spuscie"
  echo "      Skopiuj model do $ROOT/models/"
fi

chmod +x "$ROOT/start_live.sh" "$ROOT/install_autostart.sh"

# --- Stara usluga systemd pigweight-live (nie startowala: cykl zaleznosci
#     z graphical.target) — usuwamy, zeby nie bylo dwoch sposobow startu ---
OLD_UNIT="/etc/systemd/system/pigweight-live.service"
if [[ -e "$OLD_UNIT" ]]; then
  echo ">>> Usuwam stara usluge systemd pigweight-live"
  sudo systemctl disable --now pigweight-live 2>/dev/null || true
  sudo rm -f "$OLD_UNIT"
  sudo systemctl daemon-reload
fi

# --- Autostart pulpitu (po zalogowaniu — jest DISPLAY / Wayland) ---
AUTOSTART_DIR="$HOME_DIR/.config/autostart"
mkdir -p "$AUTOSTART_DIR"
DESKTOP_FILE="$AUTOSTART_DIR/pigweight-live.desktop"
cat > "$DESKTOP_FILE" <<EOF
[Desktop Entry]
Type=Application
Name=PigWeight live
Comment=Uruchamia live.py po zalogowaniu (monitor 7")
Exec=/usr/bin/env PIGWEIGHT_BOOT_DELAY=1 /bin/bash $ROOT/start_live.sh
Path=$ROOT
Terminal=false
X-GNOME-Autostart-enabled=true
EOF

echo ">>> Autostart GUI: $DESKTOP_FILE"
echo
echo "Przyciski (wlacznik I/O + spust): bash $ROOT/install_przyciski.sh"
echo
echo "Gotowe. Zrob:  sudo reboot"
echo "Po restarcie:  tail -f $ROOT/live_autostart.log"
