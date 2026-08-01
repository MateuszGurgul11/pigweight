"""Test obu przyciskow naraz (sprzet / okablowanie).

Waga (kalibracja / start):
    GPIO 26 (pin 37)  <->  przycisk  <->  GND (pin 39)

Zasilanie (wylaczanie przez overlay — ten test tylko czyta pin):
    GPIO 12 (pin 32)  <->  przycisk  <->  GND (pin 34)

Uruchomienie:
    python check/hello_buttons.py

Jesli GPIO 26 busy:
    sudo systemctl stop pigweight-live
    pkill -f 'python.*live.py' || true

Jesli GPIO 12 busy — zwykle OK (gpio-shutdown overlay); testuj wylaczenie fizycznie.
"""
import sys
import time

import board
import digitalio

WEIGHT_BUSY = """
BLAD: GPIO 26 (waga, pin 37) busy — zajety przez inny proces.

  sudo systemctl stop pigweight-live
  pkill -f 'python.*live.py' || true
  python check/hello_buttons.py
"""

try:
    weight = digitalio.DigitalInOut(board.D26)
    weight.direction = digitalio.Direction.INPUT
    weight.pull = digitalio.Pull.UP
except Exception as e:  # noqa: BLE001
    if "busy" in str(e).lower():
        print(WEIGHT_BUSY.strip())
        print(f"({type(e).__name__}: {e})")
        sys.exit(1)
    raise

power = None
try:
    p = digitalio.DigitalInOut(board.D12)
    p.direction = digitalio.Direction.INPUT
    p.pull = digitalio.Pull.UP
    power = p
    print(">>> GPIO 12 (zasilanie): wolny — moge czytac kliki w tym tescie")
except Exception as e:  # noqa: BLE001
    if "busy" in str(e).lower():
        print(
            ">>> GPIO 12 (zasilanie): zajety (prawdopodobnie gpio-shutdown) — OK.\n"
            "    Nie testuj D12 przez Python. Nacisnij przycisk 32/34 aby wylaczyc Pi\n"
            "    (wymaga: ./check/install_power_button.sh && sudo reboot)."
        )
    else:
        print(f">>> GPIO 12: blad ({type(e).__name__}: {e}) — testuje tylko wage")

print("\n=== Test przyciskow ===")
print("WAGA:      pin 37 (GPIO 26) <-> przycisk <-> pin 39 (GND)")
print("ZASILANIE: pin 32 (GPIO 12) <-> przycisk <-> pin 34 (GND)")
print("Puszczony=HIGH | Nacisniety=LOW")
print("Ctrl+C = koniec\n")

prev_w = prev_p = None
clicks_w = clicks_p = 0
last_w = last_p = 0.0

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

        if power is not None:
            p_high = bool(power.value)
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
    if power is None:
        print("  Zasilanie: nie odczytywane tu (overlay) — test fizyczny shutdown.")
    elif clicks_p == 0:
        print("  Brak ZASILANIE — sprawdz pin 32 i GND 34.")
    if clicks_w and (power is None or clicks_p):
        print("  Waga OK sprzetowo.")
    weight.deinit()
    if power is not None:
        power.deinit()
