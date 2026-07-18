"""Ekran ILI9341 (320x240 SPI) dla wagi swin — Raspberry Pi 5.

Wyswietla wynik wazenia z live.py: srednia, mediana, min/max, std oraz
wysokosc pomiaru (podloga z kalibracji).

Pi 5 ma nowy kontroler GPIO (RP1), wiec uzywamy Adafruit Blinka +
adafruit-circuitpython-rgb-display (chodzi przez lgpio).

Test okablowania (bez reszty programu):
    python display.py

Import w live.py:
    from display import PigDisplay, init_display
"""
from __future__ import annotations

from PIL import Image, ImageDraw, ImageFont

# Rozdzielczosc w orientacji poziomej (rotation=90)
WIDTH, HEIGHT = 320, 240

# Kolory (RGB)
BG = (0, 0, 0)
WHITE = (255, 255, 255)
GREY = (150, 150, 150)
GREEN = (0, 220, 90)
YELLOW = (255, 210, 0)
CYAN = (0, 200, 255)
RED = (255, 70, 70)

_FONT_PATHS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]


def _font(size: int) -> ImageFont.FreeTypeFont:
    for path in _FONT_PATHS:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


class PigDisplay:
    """Cienka warstwa nad ILI9341 — rysuje ekrany stanow i wynik."""

    def __init__(self, baudrate: int = 24_000_000, rotation: int = 90) -> None:
        # Import lokalny, zeby modul dalo sie zaladowac tez bez sprzetu
        import board
        import digitalio
        from adafruit_rgb_display import ili9341

        spi = board.SPI()
        cs = digitalio.DigitalInOut(board.CE0)
        dc = digitalio.DigitalInOut(board.D24)
        rst = digitalio.DigitalInOut(board.D25)

        self._disp = ili9341.ILI9341(
            spi, cs=cs, dc=dc, rst=rst,
            baudrate=baudrate, rotation=rotation,
        )
        self._f_big = _font(56)
        self._f_title = _font(22)
        self._f_row = _font(24)
        self._f_small = _font(18)
        self.clear()

    # --- niskopoziomowe ---

    def _push(self, img: Image.Image) -> None:
        self._disp.image(img)

    def _canvas(self) -> tuple[Image.Image, ImageDraw.ImageDraw]:
        img = Image.new("RGB", (WIDTH, HEIGHT), BG)
        return img, ImageDraw.Draw(img)

    def clear(self) -> None:
        img, _ = self._canvas()
        self._push(img)

    def _centered(self, draw, text, font, y, fill) -> None:
        w = draw.textbbox((0, 0), text, font=font)[2]
        draw.text(((WIDTH - w) // 2, y), text, font=font, fill=fill)

    # --- ekrany stanow ---

    def show_idle(self) -> None:
        img, d = self._canvas()
        self._centered(d, "WAGA SWIN", self._f_title, 70, WHITE)
        self._centered(d, "Nacisnij S / przycisk", self._f_small, 130, GREY)
        self._centered(d, "aby rozpoczac wazenie", self._f_small, 155, GREY)
        self._push(img)

    def show_calibrating(self, remaining: float, samples: int) -> None:
        img, d = self._canvas()
        self._centered(d, "KALIBRACJA SKALI", self._f_title, 80, CYAN)
        self._centered(d, f"{remaining:.1f} s", self._f_big, 115, WHITE)
        self._centered(d, f"probki podlogi: {samples}", self._f_small, 190, GREY)
        self._push(img)

    def show_measuring(self, remaining: float, count: int) -> None:
        img, d = self._canvas()
        self._centered(d, "WAZENIE...", self._f_title, 80, GREEN)
        self._centered(d, f"{remaining:.1f} s", self._f_big, 115, WHITE)
        self._centered(d, f"pomiary: {count}", self._f_small, 190, GREY)
        self._push(img)

    def show_no_pig(self) -> None:
        img, d = self._canvas()
        self._centered(d, "BRAK POMIAROW", self._f_title, 90, RED)
        self._centered(d, "nie wykryto swini", self._f_small, 130, GREY)
        self._centered(d, "Nacisnij S ponownie", self._f_small, 165, GREY)
        self._push(img)

    def show_result(self, r: dict, height_cm: float) -> None:
        """Glowny ekran wyniku. r = {n, mean, median, min, max, std}."""
        img, d = self._canvas()

        # Naglowek
        d.rectangle((0, 0, WIDTH, 30), fill=(20, 60, 30))
        self._centered(d, "WYNIK WAZENIA", self._f_title, 4, GREEN)

        # Srednia — najwazniejsza, duza czcionka
        self._centered(d, f"{r['mean']:.1f} kg", self._f_big, 36, WHITE)

        # Wiersze szczegolow
        rows = [
            ("Mediana", f"{r['median']:.1f} kg", CYAN),
            ("Min / Max", f"{r['min']:.1f} / {r['max']:.1f} kg", YELLOW),
            ("Std", f"{r['std']:.1f} kg", GREY),
            ("Wysokosc", f"{height_cm:.0f} cm", GREY),
        ]
        y = 104
        for label, value, color in rows:
            d.text((14, y), label, font=self._f_row, fill=GREY)
            vw = d.textbbox((0, 0), value, font=self._f_row)[2]
            d.text((WIDTH - 14 - vw, y), value, font=self._f_row, fill=color)
            y += 30

        # Stopka
        self._centered(d, f"{r['n']} pomiarow  |  S = ponownie", self._f_small, 224, GREY)
        self._push(img)


def init_display() -> PigDisplay | None:
    """Probuje otworzyc ekran; zwraca None gdy brak sprzetu/bibliotek.

    Dzieki temu live.py dziala tez na laptopie (tryb wideo) bez ILI9341.
    """
    try:
        disp = PigDisplay()
        print(">>> ILI9341: ekran zainicjalizowany")
        return disp
    except Exception as e:  # noqa: BLE001 — chcemy zlapac wszystko (brak board/spi/hw)
        print(f">>> ILI9341: brak ekranu ({type(e).__name__}: {e}) — kontynuuje bez wyswietlacza")
        return None


if __name__ == "__main__":
    # Test okablowania — pokazuje kolejno ekrany i przykladowy wynik
    import time

    disp = init_display()
    if disp is None:
        raise SystemExit("Nie udalo sie zainicjalizowac ekranu — sprawdz SPI i okablowanie.")

    print("Test: idle -> kalibracja -> wazenie -> wynik (co 2 s)")
    disp.show_idle();                          time.sleep(2)
    disp.show_calibrating(1.0, 42);            time.sleep(2)
    disp.show_measuring(3.0, 128);             time.sleep(2)
    disp.show_result(
        {"n": 128, "mean": 112.4, "median": 111.8, "min": 98.2, "max": 130.5, "std": 6.3},
        height_cm=245,
    )
    print("Jesli widzisz ekran wyniku — okablowanie i SPI dzialaja.")
