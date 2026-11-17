"""Test przyciskow: WLACZNIK I/O (GPIO 27, pin 13) i SPUST (GPIO 17, pin 11).

Okablowanie:
    wlacznik: zolty -> pin 13 (GPIO27), bialy  -> pin 14 (GND)
    spust:    pomaranczowy -> pin 11 (GPIO17), czarny -> pin 9 (GND)

Tylko odczyt — nic nie usypia i nie wysyla sygnalow do live.py.

Uruchomienie na Pi (usluga przyciski trzyma piny — najpierw ja zatrzymaj):
    systemctl --user stop przyciski
    python3 check/hello_przyciski.py
    systemctl --user start przyciski
"""
import sys
import time
from signal import pause

from gpiozero import Button

try:
    wlacznik = Button(27, pull_up=True, bounce_time=0.1)
    spust = Button(17, pull_up=True, bounce_time=0.05)
except Exception as e:  # noqa: BLE001
    if "busy" in str(e).lower():
        print("BLAD: GPIO busy — zatrzymaj usluge:  systemctl --user stop przyciski")
        print(f"({type(e).__name__}: {e})")
        sys.exit(1)
    raise

klikniecia = 0


def log(msg):
    print(time.strftime("%H:%M:%S"), msg, flush=True)


def na_spust():
    global klikniecia
    klikniecia += 1
    log(f"SPUST: KLIK #{klikniecia}")


wlacznik.when_pressed = lambda: log("WLACZNIK -> I")
wlacznik.when_released = lambda: log("WLACZNIK -> O")
spust.when_pressed = na_spust

print("=== Test przyciskow (gpiozero) ===")
print(f"WLACZNIK teraz: {'I' if wlacznik.is_pressed else 'O'}")
print("Przelaczaj wlacznik i naciskaj spust. Ctrl+C = koniec\n")

try:
    pause()
except KeyboardInterrupt:
    print(f"\nKoniec. Spust: {klikniecia} klikniec")
    if klikniecia == 0:
        print("  Brak klikniec — sprawdz pin 11 (GPIO17) i GND (pin 9).")
