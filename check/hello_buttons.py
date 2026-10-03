"""Test przycisku WAGI (GPIO). Zasilanie = PWR — nie da sie czytac w Pythonie.

Waga (przycisk 2):
    GPIO 12 (pin 32)  <->  przycisk  <->  GND (pin 34)

Zasilanie (przycisk 1) — zlaczze PWR na Pi 5:
    styki przycisku  <->  dwa piny PWR (J2)
    Test: nacisnij — Pi sie wylacza / wlacza. Brak odczytu GPIO.

Uruchomienie:
    python check/hello_buttons.py

Jesli GPIO 12 busy:
    sudo systemctl stop pigweight-live
    pkill -f 'python.*live.py' || true
    ./check/install_power_button.sh   # usuwa stary gpio-shutdown
    sudo reboot
"""
import sys
import time

import board
import digitalio

WEIGHT_BUSY = """
BLAD: GPIO 12 (waga, pin 32) busy — zajety przez inny proces.

  sudo systemctl stop pigweight-live
  pkill -f 'python.*live.py' || true
  ./check/install_power_button.sh && sudo reboot
  python check/hello_buttons.py
"""

try:
    weight = digitalio.DigitalInOut(board.D12)
    weight.direction = digitalio.Direction.INPUT
    weight.pull = digitalio.Pull.UP
except Exception as e:  # noqa: BLE001
    if "busy" in str(e).lower():
        print(WEIGHT_BUSY.strip())
        print(f"({type(e).__name__}: {e})")
        sys.exit(1)
    raise

print("=== Test przycisku WAGA (GPIO) ===")
print("WAGA:      pin 32 (GPIO 12) <-> przycisk <-> pin 34 (GND)")
print("ZASILANIE: przycisk 1 <-> zlaczze PWR (J2) — test fizyczny, nie GPIO")
print("Puszczony=HIGH | Nacisniety=LOW")
print("Ctrl+C = koniec\n")

prev_w = None
clicks_w = 0
last_w = 0.0

try:
    while True:
        now = time.monotonic()
        w_high = bool(weight.value)
        if w_high != prev_w:
            if prev_w is True and w_high is False and (now - last_w) > 0.2:
                clicks_w += 1
                last_w = now
                print(f">>> KLIK WAGA #{clicks_w}")
            prev_w = w_high
        time.sleep(0.03)
except KeyboardInterrupt:
    print(f"\nKoniec. Waga: {clicks_w} klikow")
    if clicks_w == 0:
        print("  Brak WAGA — sprawdz pin 32 i GND 34.")
    else:
        print("  Waga OK sprzetowo.")
    print("  Zasilanie: nacisnij przycisk 1 (PWR) — powinien wylaczyc Pi.")
    weight.deinit()
