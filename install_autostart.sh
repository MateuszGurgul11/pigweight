#!/usr/bin/env bash
# Instaluje autostart live.py po wlaczeniu Raspberry Pi.
#
# Uruchom Z folderu projektu (tam gdzie jest live.py), np.:
#   cd ~/Desktop/pigweight
#   chmod +x start_live.sh install_autostart.sh
#   ./install_autostart.sh
#   sudo reboot
#
# Logi:
#   tail -f ~/Desktop/pigweight/live_autostart.log
#   journalctl -u pigweight-live -f
# Stop:    sudo systemctl stop pigweight-live
# Disable: sudo systemctl disable pigweight-live
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
SERVICE_NAME="pigweight-live"
UNIT_SRC="$ROOT/pigweight-live.service"
UNIT_DST="/etc/systemd/system/${SERVICE_NAME}.service"
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
  echo "      (nie z Podejscie3 — ten folder juz nie istnieje)"
  exit 1
fi
if [[ ! -f "$UNIT_SRC" ]]; then
  echo "BLAD: brak $UNIT_SRC"
  exit 1
fi
if [[ ! -x "$ROOT/.venv/bin/python" && ! -x "$ROOT/venv/bin/python" ]]; then
  echo "UWAGA: brak .venv w $ROOT — autostart moze uzyc systemowego python3"
fi
if [[ ! -f "$ROOT/models/pig_seg_best.pt" ]]; then
  echo "UWAGA: brak models/pig_seg_best.pt — wazenie padnie po S/przycisku"
  echo "      Skopiuj model do $ROOT/models/"
fi

chmod +x "$ROOT/start_live.sh" "$ROOT/install_autostart.sh"

# --- 1) systemd ---
TMP="$(mktemp)"
sed \
  -e "s|/REPLACE_ROOT|$ROOT|g" \
  -e "s|/REPLACE_HOME|$HOME_DIR|g" \
  "$UNIT_SRC" > "$TMP"

# User= + Group= zaraz po [Service]
if ! grep -q "^User=" "$TMP"; then
  if sed --version >/dev/null 2>&1; then
    # GNU sed (Pi)
    sed -i "/^\[Service\]/a User=$USER_NAME\nGroup=$USER_NAME" "$TMP"
  else
    # BSD sed
    sed -i '' "/^\[Service\]/a\\
User=$USER_NAME\\
Group=$USER_NAME
" "$TMP"
  fi
fi

echo ">>> Instaluje usluge systemd: $UNIT_DST"
echo "--- zawartosc ---"
cat "$TMP"
echo "-----------------"
sudo cp "$TMP" "$UNIT_DST"
rm -f "$TMP"

sudo systemctl daemon-reload
sudo systemctl enable "$SERVICE_NAME"
sudo systemctl stop "$SERVICE_NAME" 2>/dev/null || true

# --- 2) autostart pulpitu (zapas — po zalogowaniu do GUI) ---
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
echo "Sprawdzenie enable:"
systemctl is-enabled "$SERVICE_NAME" || true
echo
echo "Gotowe. Zrob:  sudo reboot"
echo "Po restarcie:"
echo "  tail -f $ROOT/live_autostart.log"
echo "  journalctl -u $SERVICE_NAME -b --no-pager"
echo
echo "Reczny restart teraz (gdy jest pulpit):"
echo "  sudo systemctl restart $SERVICE_NAME"
