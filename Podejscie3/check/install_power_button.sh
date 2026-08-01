#!/usr/bin/env bash
# Instaluje przycisk zasilania (bezpieczny shutdown) na GPIO 12.
#
# Okablowanie:
#   pin 32 (GPIO 12)  <->  przycisk  <->  pin 34 (GND)
# (osobny od przycisku wazenia: pin 37 / GPIO 26)
#
#   cd ~/Desktop/pigweight/Podejscie3
#   chmod +x check/install_power_button.sh
#   ./check/install_power_button.sh
#   sudo reboot
#
# Po rebootcie: krotkie nacisniecie = bezpieczne wylaczenie (KEY_POWER).
set -euo pipefail

OVERLAY_LINE='dtoverlay=gpio-shutdown,gpio_pin=12,active_low=1,gpio_pull=up'
CONFIG=""
for candidate in /boot/firmware/config.txt /boot/config.txt; do
  if [[ -f "$candidate" ]]; then
    CONFIG="$candidate"
    break
  fi
done

if [[ -z "$CONFIG" ]]; then
  echo "BLAD: nie znaleziono /boot/firmware/config.txt ani /boot/config.txt"
  exit 1
fi

echo "=== Przycisk zasilania (GPIO 12 / pin 32) ==="
echo "config: $CONFIG"
echo

if grep -qE '^dtoverlay=gpio-shutdown' "$CONFIG"; then
  echo ">>> Juz jest linia gpio-shutdown w $CONFIG:"
  grep -E '^dtoverlay=gpio-shutdown' "$CONFIG" || true
  echo
  echo "Jesli gpio_pin != 12, popraw recznie na:"
  echo "  $OVERLAY_LINE"
else
  echo ">>> Dopisuje: $OVERLAY_LINE"
  echo "$OVERLAY_LINE" | sudo tee -a "$CONFIG" >/dev/null
fi

echo
echo ">>> Sprawdzam WAKE_ON_GPIO (EEPROM) — na Pi 4 budzi z halt; na Pi 5 NIE (tylko PWR)."
if command -v rpi-eeprom-config >/dev/null 2>&1; then
  WAKE="$(sudo rpi-eeprom-config 2>/dev/null | grep -E '^WAKE_ON_GPIO=' || true)"
  if [[ -z "$WAKE" ]]; then
    echo "    WAKE_ON_GPIO: (brak w config — zwykle domyslnie 1 na Pi 4)"
  else
    echo "    $WAKE"
    if [[ "$WAKE" == "WAKE_ON_GPIO=0" ]]; then
      echo
      echo "    UWAGA: WAKE_ON_GPIO=0 — na Pi 4 wlaczenie z GPIO moze nie dzialac."
      echo "    Aby ustawic 1:  sudo rpi-eeprom-config --edit"
      echo "    (zmien WAKE_ON_GPIO=1, zapisz, reboot)."
    fi
  fi
else
  echo "    (brak rpi-eeprom-config — pomijam)"
fi

echo
echo "Okablowanie:"
echo "  pin 32 (GPIO 12) <-> przycisk <-> pin 34 (GND)"
echo
echo "Zachowanie:"
echo "  WYLACZENIE: nacisnij przycisk -> bezpieczny shutdown/halt."
echo "  WLACZENIE:"
echo "    - Pi 4: czesto to samo nacisniecie (gdy WAKE_ON_GPIO=1)."
echo "    - Pi 5: GPIO nie budzi z halt — uzyj zlacza PWR na plytce"
echo "      albo odlacz/podlacz zasilanie 5V."
echo
echo "Nastepnie:  sudo reboot"
echo "Test: nacisnij przycisk zasilania — Pi powinien sie wylaczyc."
