#!/usr/bin/env bash
# Przycisk zasilania na zlaczu PWR (Pi 5) — ON + OFF bez GPIO.
#
# Okablowanie (przycisk 1 = zasilanie):
#   styki przycisku  <->  dwa piny zlacza PWR (J2) na plytce Pi 5
#   (obok USB-C; podpisane "PWR" — zwarcie = nacisk przycisku zasilania)
#
# Waga zostaje na GPIO (osobny przycisk):
#   pin 32 (GPIO 12)  <->  przycisk  <->  pin 34 (GND)
#
#   cd ~/Desktop/pigweight
#   chmod +x check/install_power_button.sh
#   ./check/install_power_button.sh
#   sudo reboot   # tylko jesli usuwamy stary gpio-shutdown
#
# Na Pi 5 zlaczem PWR:
#   krotkie nacisniecie przy wlaczonym systemie = bezpieczny shutdown
#   nacisniecie po halt = wlaczenie (GPIO tego nie umie)
set -euo pipefail

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

echo "=== Przycisk zasilania = zlaczze PWR (Pi 5) ==="
echo "config: $CONFIG"
echo

NEED_REBOOT=0
if grep -qE '^dtoverlay=gpio-shutdown' "$CONFIG"; then
  echo ">>> Usuwam stary overlay gpio-shutdown (niepotrzebny przy PWR):"
  grep -E '^dtoverlay=gpio-shutdown' "$CONFIG" || true
  sudo sed -i.bak -E '/^dtoverlay=gpio-shutdown/d' "$CONFIG"
  NEED_REBOOT=1
  echo ">>> Usunieto. GPIO 12/26 wolne dla wagi / innych zastosowan."
else
  echo ">>> Brak dtoverlay=gpio-shutdown — OK (PWR nie wymaga overlay)."
fi

echo
echo "Okablowanie:"
echo "  PRZYCISK 1 (ZASILANIE): styki przycisku <-> dwa piny PWR (J2) na Pi 5"
echo "  PRZYCISK 2 (WAGA):      pin 32 (GPIO 12) <-> przycisk <-> pin 34 (GND)"
echo
echo "Zachowanie (PWR):"
echo "  WYLACZENIE: krotkie nacisniecie przy dzialajacym systemie -> shutdown"
echo "  WLACZENIE:  nacisniecie gdy Pi jest w halt -> start"
echo "  (nie uzywaj pinow 37/39 do zasilania — to juz nie GPIO shutdown)"
echo

if [[ "$NEED_REBOOT" -eq 1 ]]; then
  echo "=============================================="
  echo "  Wymagane:  sudo reboot"
  echo "  (zeby zwolnic GPIO po usunieciu overlay)"
  echo "=============================================="
else
  echo "Reboot nie jest wymagany — podlacz przycisk 1 pod PWR i testuj."
fi
echo
echo "Test wagi (GPIO):  python check/hello_button.py"
echo "Zasilanie: nacisnij przycisk 1 — powinien wylaczyc / wlaczyc Pi."
