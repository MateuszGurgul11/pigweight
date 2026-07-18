"""Najprostszy test ekranu ILI9341 na Raspberry Pi 5.

Uruchamia wyswietlacz i pokazuje napis. Nic wiecej — do sprawdzenia,
czy okablowanie i SPI dzialaja.

    python hello_screen.py

Wymaga (na Pi):
    pip install adafruit-circuitpython-rgb-display adafruit-blinka pillow
    oraz wlaczonego SPI (sudo raspi-config -> Interface Options -> SPI).
"""
import board
import digitalio
from adafruit_rgb_display import ili9341
from PIL import Image, ImageDraw, ImageFont

# --- inicjalizacja ekranu ---
spi = board.SPI()
cs = digitalio.DigitalInOut(board.CE0)    # CS  -> pin 24
dc = digitalio.DigitalInOut(board.D24)    # DC  -> pin 18
rst = digitalio.DigitalInOut(board.D25)   # RST -> pin 22

disp = ili9341.ILI9341(spi, cs=cs, dc=dc, rst=rst, baudrate=24_000_000, rotation=90)

WIDTH, HEIGHT = 320, 240  # orientacja pozioma (rotation=90)

# --- rysowanie ---
img = Image.new("RGB", (WIDTH, HEIGHT), (0, 0, 0))  # czarne tlo
draw = ImageDraw.Draw(img)

try:
    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 40)
except OSError:
    font = ImageFont.load_default()

text = "DZIALA!"
w = draw.textbbox((0, 0), text, font=font)[2]
draw.text(((WIDTH - w) // 2, 90), text, font=font, fill=(0, 220, 90))  # zielony napis

disp.image(img)  # wyslij na ekran
print("Napis wyswietlony na ILI9341.")
