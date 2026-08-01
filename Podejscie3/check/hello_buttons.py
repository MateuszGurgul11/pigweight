"""Test obu przyciskow naraz (sprzet / okablowanie).

Waga (kalibracja / start):
    GPIO 12 (pin 32)  <->  przycisk  <->  GND (pin 34)

Zasilanie (wylaczanie przez overlay — ten test tylko czyta pin):
    GPIO 26 (pin 37)  <->  przycisk  <->  GND (pin 39)

Uruchomienie:
    python check/hello_buttons.py

Jesli GPIO 12 busy:
    sudo systemctl stop pigweight-live
    pkill -f 'python.*live.py' || true
    # oraz upewnij sie, ze gpio-shutdown jest na pin 26 (nie 12)

Jesli GPIO 26 busy — zwykle OK (gpio-shutdown overlay); testuj wylaczenie fizycznie.
"""
import sys
import time

import board
import digitalio

WEIGHT_BUSY = """
BLAD: GPIO 12 (waga, pin 32) busy — zajety przez inny proces.

  sudo systemctl stop pigweight-live
  pkill -f 'python.*live.py' || true
  # jesli stary overlay na gpio_pin=12: ./check/install_power_button.sh && sudo reboot
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

power = None
try:
    p = digitalio.DigitalInOut(board.D26)
    p.direction = digitalio.Direction.INPUT
    p.pull = digitalio.Pull.UP
    power = p
    print(">>> GPIO 26 (zasilanie): wolny — moge czytac kliki w tym tescie")
except Exception as e:  # noqa: BLE001
    if "busy" in str(e).lower():
        print(
            ">>> GPIO 26 (zasilanie): zajety (prawdopodobnie gpio-shutdown) — OK.\n"
            "    Nie testuj D26 przez Python. Nacisnij przycisk 37/39 aby wylaczyc Pi\n"
            "    (wymaga: ./check/install_power_button.sh && sudo reboot)."
        )
    else:
        print(f">>> GPIO 26: blad ({type(e).__name__}: {e}) — testuje tylko wage")

print("\n=== Test przyciskow ===")
print("WAGA:      pin 32 (GPIO 12) <-> przycisk <-> pin 34 (GND)")
print("ZASILANIE: pin 37 (GPIO 26) <-> przycisk <-> pin 39 (GND)")
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
        print("  Brak WAGA — sprawdz pin 32 i GND 34.")
    if power is None:
        print("  Zasilanie: nie odczytywane tu (overlay) — test fizyczny shutdown.")
    elif clicks_p == 0:
        print("  Brak ZASILANIE — sprawdz pin 37 i GND 39.")
    if clicks_w and (power is None or clicks_p):
        print("  Waga OK sprzetowo.")
    weight.deinit()
    if power is not None:
        power.deinit()
