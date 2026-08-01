"""Test fizycznego przycisku WAZENIA na GPIO 12 (pin 32).

Okablowanie (waga / przycisk 2):
    GPIO 12 (fizyczny pin 32)  <->  przycisk  <->  GND (pin 34)

Przycisk ZASILANIA (przycisk 1) — NIE na GPIO:
    styki przycisku  <->  dwa piny zlacza PWR (J2) na Pi 5
    Instalacja / usuniecie starego overlay: ./check/install_power_button.sh

Uruchomienie na Pi:
    python check/hello_button.py

Jesli 'GPIO busy':
    sudo systemctl stop pigweight-live
    pkill -f 'python.*live.py' || true
    # jesli stary gpio-shutdown: ./check/install_power_button.sh && sudo reboot
"""
import sys
import time

import board
import digitalio

PIN = board.D12  # BCM 12 = fizyczny pin 32

BUSY_HINT = """
BLAD: GPIO busy — pin 32 (GPIO 12) jest zajety przez inny proces.

Zatrzymaj konflikt i sprobuj ponownie:
  sudo systemctl stop pigweight-live
  pkill -f 'python.*live.py' || true
  python check/hello_button.py

Jesli masz stary overlay gpio-shutdown — usun go:
  ./check/install_power_button.sh && sudo reboot
"""

try:
    btn = digitalio.DigitalInOut(PIN)
    btn.direction = digitalio.Direction.INPUT
    btn.pull = digitalio.Pull.UP
except Exception as e:  # noqa: BLE001
    if "busy" in str(e).lower():
        print(BUSY_HINT.strip())
        print(f"({type(e).__name__}: {e})")
        sys.exit(1)
    raise

print("=== Test przycisku GPIO 12 (pin 32) — WAGA ===")
print("Podlaczenie: pin 32 <-> przycisk <-> GND (pin 34)")
print("Zasilanie (przycisk 1): zlaczze PWR na Pi 5 — nie ten test")
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
            "Brak klikniec — sprawdz przewody pin 32 i GND (pin 34) "
            "oraz czy przycisk zwiera styki przy nacisku."
        )
    btn.deinit()
