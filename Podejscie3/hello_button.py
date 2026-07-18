"""Test fizycznego przycisku na GPIO 3 (pin 5).

Okablowanie (jak u Ciebie):
    GPIO 3 (fizyczny pin 5)  <->  przycisk  <->  GND (pin 9)

Uruchomienie na Pi:
    python hello_button.py

Bez nacisku powinno byc HIGH / puszczony.
Po nacisnieciu — LOW / NACISNIETY (oraz licznik ++).
Ctrl+C konczy.
"""
import time

import board
import digitalio

PIN = board.D3  # BCM 3 = fizyczny pin 5

btn = digitalio.DigitalInOut(PIN)
btn.direction = digitalio.Direction.INPUT
btn.pull = digitalio.Pull.UP

print("=== Test przycisku GPIO 3 (pin 5) ===")
print("Podlaczenie: pin 5 <-> przycisk <-> GND (pin 9)")
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
            "Brak klikniec — sprawdz przewody pin 5 i GND (pin 9) "
            "oraz czy przycisk zwiera styki przy nacisku."
        )
    btn.deinit()
