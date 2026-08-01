#!/usr/bin/env bash
# Instaluje przycisk zasilania (bezpieczny shutdown) na GPIO 26.
#
# Okablowanie:
#   pin 37 (GPIO 26)  <->  przycisk  <->  pin 39 (GND)
# (osobny od przycisku wazenia: pin 32 / GPIO 12)
#
#   cd ~/Desktop/pigweight/Podejscie3
#   chmod +x check/install_power_button.sh
#   ./check/install_power_button.sh
#   sudo reboot          # WYMAGANE — bez rebootu overlay NIE dziala
#
# Po rebootcie: krotkie nacisniecie = bezpieczne wylaczenie (KEY_POWER).
set -euo pipefail

echo "=============================================="
echo "  UWAGA: po tej instalacji MUSISZ zrobic:"
echo "         sudo reboot"
echo "  Bez rebootu przycisk zasilania NIE zadziala."
echo "=============================================="
echo

OVERLAY_LINE='dtoverlay=gpio-shutdown,gpio_pin=26,active_low=1,gpio_pull=up'
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

echo "=== Przycisk zasilania (GPIO 26 / pin 37) ==="
echo "config: $CONFIG"
echo

if grep -qE '^dtoverlay=gpio-shutdown' "$CONFIG"; then
  echo ">>> Znaleziono istniejaca linie gpio-shutdown:"
  grep -E '^dtoverlay=gpio-shutdown' "$CONFIG" || true
  if grep -qE '^dtoverlay=gpio-shutdown,gpio_pin=26' "$CONFIG"; then
    echo ">>> Juz gpio_pin=26 — OK."
  else
    echo ">>> Podmieniam na gpio_pin=26 (waga jest na GPIO 12)..."
    sudo sed -i.bak -E 's/^dtoverlay=gpio-shutdown.*/'"$OVERLAY_LINE"'/' "$CONFIG"
    echo ">>> Nowa linia:"
    grep -E '^dtoverlay=gpio-shutdown' "$CONFIG" || true
  fi
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
echo "  ZASILANIE: pin 37 (GPIO 26) <-> przycisk <-> pin 39 (GND)"
echo "  WAGA:      pin 32 (GPIO 12) <-> przycisk <-> pin 34 (GND)"
echo
echo "Zachowanie:"
echo "  WYLACZENIE: nacisnij przycisk zasilania -> bezpieczny shutdown/halt."
echo "  WLACZENIE:"
echo "    - Pi 4: czesto to samo nacisniecie (gdy WAKE_ON_GPIO=1)."
echo "    - Pi 5: GPIO nie budzi z halt — uzyj zlacza PWR na plytce"
echo "      albo odlacz/podlacz zasilanie 5V."
echo
echo "=============================================="
echo "  TERAZ OBOWIAZKOWO:  sudo reboot"
echo "  Bez tego overlay gpio-shutdown nie jest aktywny"
echo "  i przycisk zasilania nic nie zrobi."
echo "=============================================="
echo
echo "Po reboocie: nacisnij przycisk na pin 37/39 — Pi powinien sie wylaczyc."
echo "Test sprzetu (oba przyciski):  python check/hello_buttons.py"
