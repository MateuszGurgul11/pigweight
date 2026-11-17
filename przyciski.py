#!/usr/bin/env python3
"""
Obsluga dwoch przyciskow na Raspberry Pi 5 (jedyny proces, ktory czyta GPIO).

WLACZNIK (kolyskowy I/O)  - zolty -> pin 13 (GPIO27), bialy -> pin 14 (GND)
    I = Pi pracuje normalnie
    O = "uspienie": gasnie ekran, wylaczone Wi-Fi/Bluetooth,
        procesor w trybie oszczednym, trwajace wazenie przerwane,
        spust nic nie robi

SPUST (pomiar)            - pomaranczowy -> pin 32 (GPIO12), czarny -> pin 34 (GND)
    wcisniecie = start wazenia w dzialajacym live.py (sygnal SIGUSR1)

live.py dziala caly czas (start_live.sh z autostartu) i trzyma kamere OAK-D,
dlatego spust nie uruchamia nowego programu, tylko wysyla sygnal:
    SIGUSR1 -> start wazenia (jak klawisz S)
    SIGUSR2 -> przerwij wazenie (wlacznik -> O)

Test reczny:   python3 przyciski.py   (najpierw: systemctl --user stop przyciski)
Instalacja:    bash install_przyciski.sh
"""

import glob
import os
import signal
import subprocess
import threading
import time
import traceback
from signal import pause

from gpiozero import Button

# ---------------- USTAWIENIA ----------------
PIN_WLACZNIK = 27   # pin fizyczny 13
PIN_SPUST = 12      # pin fizyczny 32 (GND: pin 34)

# Nazwa wyjscia ekranu. None = wykryj przy kazdym usypianiu (komenda: wlr-randr).
EKRAN = None

# Ponawianie gaszenia ekranu, gdy pulpit jeszcze nie wstal (start z wlacznikiem na O)
EKRAN_PROBY = 24
EKRAN_ODSTEP_S = 5.0
# --------------------------------------------

# Dostep do ekranu (Wayland) takze gdy skrypt startuje jako usluga.
os.environ.setdefault("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
os.environ.setdefault("WAYLAND_DISPLAY", "wayland-0")

GOVERNOR = "/sys/devices/system/cpu/cpufreq/policy0/scaling_governor"

uspiony = False
ekran_wylaczony = None   # nazwa wyjscia zgaszonego przez usyp() (do obudz())
lock = threading.RLock()


def log(msg):
    print(time.strftime("%H:%M:%S"), msg, flush=True)


def sh(cmd):
    """Uruchom polecenie powloki; bledy tylko logujemy, nie przerywamy."""
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if r.returncode != 0:
        log(f"  (ostrzezenie) '{cmd}': {r.stderr.strip()}")
    return r


def wykryj_ekran():
    """Pierwsze wyjscie z listy wlr-randr (np. HDMI-A-1, DSI-1); None gdy pulpit nie dziala."""
    if EKRAN:
        return EKRAN
    r = subprocess.run("wlr-randr", shell=True, capture_output=True, text=True)
    for linia in r.stdout.splitlines():
        if linia and not linia.startswith(" "):
            return linia.split()[0]
    return None


def czytaj_governor():
    try:
        with open(GOVERNOR) as f:
            return f.read().strip()
    except OSError:
        return "ondemand"


GOVERNOR_NORMALNY = czytaj_governor()
if GOVERNOR_NORMALNY == "powersave":
    GOVERNOR_NORMALNY = "ondemand"


def ustaw_governor(tryb):
    for plik in glob.glob("/sys/devices/system/cpu/cpufreq/policy*/scaling_governor"):
        sh(f"echo {tryb} | sudo tee {plik} > /dev/null")


def pid_live():
    """PID-y procesow 'python ... live.py' tego samego uzytkownika."""
    pidy = []
    for sciezka in glob.glob("/proc/[0-9]*/cmdline"):
        try:
            if os.stat(sciezka).st_uid != os.getuid():
                continue
            with open(sciezka, "rb") as f:
                argv = f.read().split(b"\0")
        except OSError:
            continue
        if not argv or b"python" not in os.path.basename(argv[0]):
            continue
        if any(os.path.basename(a) == b"live.py" for a in argv[1:]):
            pidy.append(int(sciezka.split("/")[2]))
    return pidy


def wyslij_do_live(sig, opis):
    pidy = pid_live()
    if not pidy:
        log(f"  brak dzialajacego live.py — {opis} pominiety")
        return
    for pid in pidy:
        try:
            os.kill(pid, sig)
            log(f"  {opis} -> live.py (pid {pid})")
        except OSError as e:
            log(f"  nie udalo sie wyslac sygnalu do pid {pid}: {e}")


def zgas_ekran(proba=1):
    """Gasi ekran; gdy pulpit jeszcze nie dziala, ponawia co EKRAN_ODSTEP_S."""
    global ekran_wylaczony
    with lock:
        if not uspiony or ekran_wylaczony:
            return
        nazwa = wykryj_ekran()
        if nazwa and sh(f"wlr-randr --output {nazwa} --off").returncode == 0:
            ekran_wylaczony = nazwa
            log(f"  ekran {nazwa} wylaczony")
            return
    if proba < EKRAN_PROBY:
        t = threading.Timer(EKRAN_ODSTEP_S, zgas_ekran, args=(proba + 1,))
        t.daemon = True
        t.start()
    else:
        log("  nie udalo sie zgasic ekranu (wlr-randr) — sprawdz sesje Wayland")


def usyp():
    global uspiony
    with lock:
        if uspiony:
            return
        uspiony = True
    log("WLACZNIK -> O : usypiam")
    wyslij_do_live(signal.SIGUSR2, "przerwanie wazenia")
    zgas_ekran()
    sh("sudo rfkill block wifi")
    sh("sudo rfkill block bluetooth")
    ustaw_governor("powersave")


def obudz():
    global uspiony, ekran_wylaczony
    with lock:
        if not uspiony:
            return
        uspiony = False
        nazwa, ekran_wylaczony = ekran_wylaczony, None
    log("WLACZNIK -> I : budze")
    ustaw_governor(GOVERNOR_NORMALNY)
    sh("sudo rfkill unblock wifi")
    sh("sudo rfkill unblock bluetooth")
    nazwa = nazwa or wykryj_ekran()
    if nazwa:
        sh(f"wlr-randr --output {nazwa} --on")


def pomiar():
    if uspiony:
        log("SPUST: pominiety (urzadzenie uspione)")
        return
    log("SPUST: start wazenia")
    wyslij_do_live(signal.SIGUSR1, "start wazenia")


def bezpiecznie(fn):
    """Blad w obsludze przycisku tylko logujemy — nie moze zablokowac kolejnych nacisniec."""
    def wrapper():
        try:
            fn()
        except Exception:  # noqa: BLE001
            log(f"BLAD w {fn.__name__}:")
            traceback.print_exc()
    return wrapper


def main():
    log(f"Start. Ekran: {EKRAN or 'auto (wlr-randr)'}, governor: {GOVERNOR_NORMALNY}")

    wlacznik = Button(PIN_WLACZNIK, pull_up=True, bounce_time=0.1)
    spust = Button(PIN_SPUST, pull_up=True, bounce_time=0.05)

    wlacznik.when_pressed = bezpiecznie(obudz)    # styk zwarty   = pozycja I
    wlacznik.when_released = bezpiecznie(usyp)    # styk rozwarty = pozycja O
    spust.when_pressed = bezpiecznie(pomiar)

    # Stan wlacznika w chwili startu
    if not wlacznik.is_pressed:
        bezpiecznie(usyp)()
    else:
        log("WLACZNIK w pozycji I : praca normalna")

    pause()


if __name__ == "__main__":
    main()
