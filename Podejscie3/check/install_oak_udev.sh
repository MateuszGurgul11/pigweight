#!/usr/bin/env bash
# Instaluje reguly udev Luxonis/Movidius (vendor 03e7), zeby DepthAI
# mogl otworzyc OAK-D bez root (bez "Insufficient permissions" /
# "No available devices").
#
#   cd ~/Desktop/pigweight/Podejscie3
#   chmod +x check/install_oak_udev.sh
#   ./check/install_oak_udev.sh
#
# Potem OBOWIAZKOWO: odlacz i podlacz kabel OAK-D (albo reboot),
# potem: python live.py
set -euo pipefail

RULES_FILE="/etc/udev/rules.d/80-movidius.rules"
RULE='SUBSYSTEM=="usb", ATTRS{idVendor}=="03e7", MODE="0666"'

echo "=== Instalacja udev dla OAK-D (Luxonis / Movidius 03e7) ==="
echo "Plik: $RULES_FILE"
echo

echo "$RULE" | sudo tee "$RULES_FILE" >/dev/null
sudo chmod 644 "$RULES_FILE"
sudo udevadm control --reload-rules
sudo udevadm trigger

echo
echo "Gotowe. Zawartosc reguly:"
cat "$RULES_FILE"
echo
echo "USB (jesli podlaczone):"
lsusb 2>/dev/null | grep -iE '03e7|Luxonis|Movidius' || echo "  (brak 03e7 w lsusb — podlacz kamere)"
echo
echo "NASTEPNIE:"
echo "  1) Odłącz i podłącz kabel OAK-D (albo: sudo reboot)"
echo "  2) cd do Podejscie3 && source venv/bin/activate && python live.py"
echo "  3) sudo systemctl restart pigweight-live   # jesli uzywasz autostartu"
echo
echo "Jesli nadal 'Insufficient permissions' — sprawdz:"
echo "  ls -l $RULES_FILE"
echo "  i czy po odlaczeniu/podlaczeniu USB warning zniknal."
