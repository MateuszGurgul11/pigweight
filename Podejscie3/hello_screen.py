"""Najprostszy test ekranu ILI9341 na Raspberry Pi 5.

Uruchamia wyswietlacz i pokazuje napis. Nic wiecej — do sprawdzenia,
czy okablowanie i SPI dzialaja.

    python hello_screen.py

Wymaga (na Pi):
    pip install adafruit-circuitpython-rgb-display adafruit-blinka pillow
    oraz wlaczonego SPI (sudo raspi-config -> Interface Options -> SPI).

Pi 5 + CS na CE0 (pin 24): kernel zajmuje CE0 jako spi0 CS0, wiec
DigitalInOut(board.CE0) rzuca lgpio.error: 'GPIO busy'. Zwolnij CE0/CE1
ze sterownika SPI (SPI zostaje aktywne), dodajac do /boot/firmware/config.txt:

    dtoverlay=spi0-0cs

Potem reboot. Alternatywa: skrypt Adafruit raspi-spi-reassign.py
z --ce0=disabled --ce1=disabled.
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

disp = ili9341.ILI9341(spi, cs=cs, dc=dc, rst=rst, baudrate=24_000_000, rotation=0)

WIDTH, HEIGHT = 240, 320  # orientacja pionowa (native ILI9341)

# --- rysowanie ---
img = Image.new("RGB", (WIDTH, HEIGHT), (0, 0, 0))  # czarne tlo
draw = ImageDraw.Draw(img)

try:
    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 40)
except OSError:
    font = ImageFont.load_default()

text = "DZIALA!"
w = draw.textbbox((0, 0), text, font=font)[2]
draw.text(((WIDTH - w) // 2, 140), text, font=font, fill=(0, 220, 90))  # zielony napis

disp.image(img)  # wyslij na ekran
print("Napis wyswietlony na ILI9341.")
