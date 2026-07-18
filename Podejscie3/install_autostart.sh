#!/usr/bin/env bash
# Instaluje autostart live.py po wlaczeniu Raspberry Pi.
#
# Pliki maja zostac W TYM folderze (np. ~/Desktop/pigweight/Podejscie3).
# Nie przenosisz ich do /etc — instalator sam tworzy usluge systemd
# wskazujaca na ta sciezke.
#
#   cd ~/Desktop/pigweight/Podejscie3
#   chmod +x start_live.sh install_autostart.sh
#   ./install_autostart.sh
#   sudo reboot
#
# Logi:
#   tail -f ~/Desktop/pigweight/Podejscie3/live_autostart.log
#   journalctl -u pigweight-live -f
# Stop:    sudo systemctl stop pigweight-live
# Disable: sudo systemctl disable pigweight-live
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
SERVICE_NAME="pigweight-live"
UNIT_SRC="$ROOT/pigweight-live.service"
UNIT_DST="/etc/systemd/system/${SERVICE_NAME}.service"
USER_NAME="$(id -un)"
HOME_DIR="$(getent passwd "$USER_NAME" | cut -d: -f6)"
HOME_DIR="${HOME_DIR:-$HOME}"

echo "=========================================="
echo "  PigWeight — instalacja autostartu"
echo "=========================================="
echo "Folder projektu (tu maja byc skrypty):"
echo "  $ROOT"
echo "Uzytkownik: $USER_NAME"
echo "HOME:       $HOME_DIR"
echo

if [[ ! -f "$ROOT/live.py" ]]; then
  echo "BLAD: w $ROOT nie ma live.py — uruchom instalator z folderu Podejscie3"
  exit 1
fi
if [[ ! -f "$UNIT_SRC" ]]; then
  echo "BLAD: brak $UNIT_SRC"
  exit 1
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
  sed -i "/^\[Service\]/a User=$USER_NAME\nGroup=$USER_NAME" "$TMP"
fi

echo ">>> Instaluje usluge systemd: $UNIT_DST"
echo "--- zawartosc ---"
cat "$TMP"
echo "-----------------"
sudo cp "$TMP" "$UNIT_DST"
rm -f "$TMP"

sudo systemctl daemon-reload
sudo systemctl enable "$SERVICE_NAME"
# Nie restartuj teraz na sile jesli brak DISPLAY — enable wystarczy do bootu
sudo systemctl stop "$SERVICE_NAME" 2>/dev/null || true

# --- 2) autostart pulpitu (zapas — dziala po zalogowaniu do GUI) ---
AUTOSTART_DIR="$HOME_DIR/.config/autostart"
mkdir -p "$AUTOSTART_DIR"
DESKTOP_FILE="$AUTOSTART_DIR/pigweight-live.desktop"
cat > "$DESKTOP_FILE" <<EOF
[Desktop Entry]
Type=Application
Name=PigWeight live
Comment=Uruchamia live.py po zalogowaniu
Exec=/bin/bash $ROOT/start_live.sh
Path=$ROOT
Terminal=false
X-GNOME-Autostart-enabled=true
EOF
# PIGWEIGHT_BOOT_DELAY dla .desktop tez
# (nadpisz Exec z env)
cat > "$DESKTOP_FILE" <<EOF
[Desktop Entry]
Type=Application
Name=PigWeight live
Comment=Uruchamia live.py po zalogowaniu
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
echo "Po restarcie sprawdz log:"
echo "  tail -f $ROOT/live_autostart.log"
echo "albo:"
echo "  journalctl -u $SERVICE_NAME -b --no-pager"
