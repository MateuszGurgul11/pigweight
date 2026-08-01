"""Test obu przyciskow naraz (sprzet / okablowanie).

Waga (kalibracja / start):
    GPIO 26 (pin 37)  <->  przycisk  <->  GND (pin 39)

Zasilanie (wylaczanie przez overlay — ten test tylko czyta pin):
    GPIO 12 (pin 32)  <->  przycisk  <->  GND (pin 34)

Uruchomienie:
    python check/hello_buttons.py

Przy nacisku (LOW) wypisze KLIK WAGA / KLIK ZASILANIE.
Ctrl+C konczy.

Uwaga: zasilanie w systemie dziala dopiero po:
    ./check/install_power_button.sh && sudo reboot
"""
import time

import board
import digitalio

WEIGHT = digitalio.DigitalInOut(board.D26)  # pin 37
POWER = digitalio.DigitalInOut(board.D12)   # pin 32

for pin in (WEIGHT, POWER):
    pin.direction = digitalio.Direction.INPUT
    pin.pull = digitalio.Pull.UP

print("=== Test przyciskow ===")
print("WAGA:      pin 37 (GPIO 26) <-> przycisk <-> pin 39 (GND)")
print("ZASILANIE: pin 32 (GPIO 12) <-> przycisk <-> pin 34 (GND)")
print("Puszczony=HIGH | Nacisniety=LOW")
print("Ctrl+C = koniec\n")

prev_w = prev_p = None
clicks_w = clicks_p = 0
last_w = last_p = 0.0

try:
    while True:
        w_high = bool(WEIGHT.value)
        p_high = bool(POWER.value)
        now = time.monotonic()

        if w_high != prev_w:
            if prev_w is True and w_high is False and (now - last_w) > 0.2:
                clicks_w += 1
                last_w = now
                print(f">>> KLIK WAGA #{clicks_w}")
            prev_w = w_high

        if p_high != prev_p:
            if prev_p is True and p_high is False and (now - last_p) > 0.2:
                clicks_p += 1
                last_p = now
                print(f">>> KLIK ZASILANIE #{clicks_p}")
            prev_p = p_high

        time.sleep(0.03)
except KeyboardInterrupt:
    print(f"\nKoniec. Waga: {clicks_w} klikow | Zasilanie: {clicks_p} klikow")
    if clicks_w == 0:
        print("  Brak WAGA — sprawdz pin 37 i GND 39.")
    if clicks_p == 0:
        print("  Brak ZASILANIE — sprawdz pin 32 i GND 34.")
    if clicks_w and clicks_p:
        print("  Oba OK sprzetowo. Zasilanie w OS: ./check/install_power_button.sh && sudo reboot")
    WEIGHT.deinit()
    POWER.deinit()
