#!/usr/bin/env bash
# Instaluje autostart live.py po wlaczeniu Raspberry Pi (systemd).
#
#   cd Podejscie3
#   chmod +x start_live.sh install_autostart.sh
#   ./install_autostart.sh
#
# Potem: sudo reboot
# Logi:   journalctl -u pigweight-live -f
# Stop:   sudo systemctl stop pigweight-live
# Disable: sudo systemctl disable pigweight-live
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
SERVICE_NAME="pigweight-live"
UNIT_SRC="$ROOT/pigweight-live.service"
UNIT_DST="/etc/systemd/system/${SERVICE_NAME}.service"
USER_NAME="$(id -un)"
HOME_DIR="$(eval echo "~$USER_NAME")"

chmod +x "$ROOT/start_live.sh"

TMP="$(mktemp)"
sed \
  -e "s|/REPLACE_ROOT|$ROOT|g" \
  -e "s|/REPLACE_HOME|$HOME_DIR|g" \
  "$UNIT_SRC" > "$TMP"

# Wstaw User= pod [Service]
if ! grep -q "^User=" "$TMP"; then
  sed -i "/^\[Service\]/a User=$USER_NAME" "$TMP"
fi

echo ">>> Instaluje $UNIT_DST"
echo "    Root: $ROOT"
echo "    User: $USER_NAME"
sudo cp "$TMP" "$UNIT_DST"
rm -f "$TMP"

sudo systemctl daemon-reload
sudo systemctl enable "$SERVICE_NAME"
sudo systemctl restart "$SERVICE_NAME" || true

echo
echo "Gotowe. Status:"
systemctl --no-pager status "$SERVICE_NAME" || true
echo
echo "Po restarcie Pi live.py wystartuje sam."
echo "Logi na zywo: journalctl -u $SERVICE_NAME -f"
