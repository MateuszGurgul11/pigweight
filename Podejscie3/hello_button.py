"""Test fizycznego przycisku na GPIO 17 (pin 11).

Okablowanie:
    GPIO 17 (fizyczny pin 11)  <->  przycisk  <->  GND (np. pin 9)

Uruchomienie na Pi:
    python hello_button.py

Bez nacisku powinno byc HIGH / puszczony.
Po nacisnieciu — LOW / NACISNIETY (oraz licznik ++).
Ctrl+C konczy.
"""
import time

import board
import digitalio

PIN = board.D17  # BCM 17 = fizyczny pin 11

btn = digitalio.DigitalInOut(PIN)
btn.direction = digitalio.Direction.INPUT
btn.pull = digitalio.Pull.UP

print("=== Test przycisku GPIO 17 (pin 11) ===")
print("Podlaczenie: pin 11 <-> przycisk <-> GND")
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
            # zbocze opadajace = naciśnięcie (przy pull-up)
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
            "Brak klikniec — sprawdz:\n"
            "  1) przewody na pin 11 i GND\n"
            "  2) czy to na pewno fizyczny pin 11 (nie 'GPIO17' na zlej nakladce)\n"
            "  3) czy przycisk ma zwarcie przy nacisku (multimetr / inny pin)"
        )
    btn.deinit()
