"""Test fizycznego przycisku WAZENIA na GPIO 26 (pin 37).

Okablowanie (wazenie):
    GPIO 26 (fizyczny pin 37)  <->  przycisk  <->  GND (pin 39)

Przycisk ZASILANIA to osobny przycisk:
    GPIO 12 (fizyczny pin 32)  <->  przycisk  <->  GND (pin 34)
    Instalacja: ./check/install_power_button.sh

Uruchomienie na Pi:
    python check/hello_button.py

Jesli 'GPIO busy':
    sudo systemctl stop pigweight-live
    pkill -f 'python.*live.py' || true
    # potem ponownie: python check/hello_button.py
"""
import sys
import time

import board
import digitalio

PIN = board.D26  # BCM 26 = fizyczny pin 37

BUSY_HINT = """
BLAD: GPIO busy — pin 37 (GPIO 26) jest zajety przez inny proces.

Zatrzymaj konflikt i sprobuj ponownie:
  sudo systemctl stop pigweight-live
  pkill -f 'python.*live.py' || true
  python check/hello_button.py
"""

try:
    btn = digitalio.DigitalInOut(PIN)
    btn.direction = digitalio.Direction.INPUT
    btn.pull = digitalio.Pull.UP
except Exception as e:  # noqa: BLE001
    msg = str(e).lower()
    if "busy" in msg or "GPIO busy" in str(e):
        print(BUSY_HINT.strip())
        print(f"({type(e).__name__}: {e})")
        sys.exit(1)
    raise

print("=== Test przycisku GPIO 26 (pin 37) ===")
print("Podlaczenie: pin 37 <-> przycisk <-> GND (pin 39)")
print("Puszczony = HIGH | Nacisniety = LOW")
print("Ctrl+C = koniec\n")

prev = None
presses = 0
last_edge = 0.0

try:
    while True:
        high = bool(btn.value)
        label = "HIGH  (puszczony)" if high else "LOW   (NACISNIETY)"
        now = time.monotonic()

        if high != prev:
            if prev is True and high is False and (now - last_edge) > 0.2:
                presses += 1
                last_edge = now
                print(f">>> KLIK #{presses}  |  {label}")
            else:
                print(f"    stan: {label}")
            prev = high

        time.sleep(0.03)
except KeyboardInterrupt:
    print(f"\nKoniec. Wykryte klikniecia: {presses}")
    if presses == 0:
        print(
            "Brak klikniec — sprawdz przewody pin 37 i GND (pin 39) "
            "oraz czy przycisk zwiera styki przy nacisku."
        )
    btn.deinit()
