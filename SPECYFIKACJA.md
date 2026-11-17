# PigWeight — specyfikacja techniczna

> Stan na: commit `29f80fe` (2026-10-03) + poprawki z 2026-10-18 (pkt 10). Dokument opisuje kod w repozytorium tak, jak działa obecnie.

## 1. Cel projektu

**PigWeight** (w kodzie też „WagaSwin”) to bezdotykowa waga dla świń. Zamiast wprowadzać zwierzę na wagę mechaniczną, kamera zawieszona pionowo nad kojcem/korytarzem robi zdjęcie z góry, model sieci neuronowej wycina sylwetkę świni, a waga jest szacowana z pola powierzchni grzbietu (lub przybliżonej objętości) przeliczonego na centymetry.

Docelowe urządzenie to samodzielny terminal:

- **Raspberry Pi 5** + kamera stereo **Luxonis OAK-D S2** (RGB + głębia),
- **monitor 7″ 1024×600** ustawiony pionowo,
- **spust** (start ważenia) i **włącznik kołyskowy I/O** (usypianie) na GPIO, obsługiwane przez `przyciski.py`,
- aplikacja `live.py` startuje sama po włączeniu prądu (systemd).

Operator naciska spust → ~1 s kalibracji skali + 3 s pomiaru → na ekranie pojawia się wynik w kg.

Działają dwa programy: `live.py` (kamera, ważenie, ekran) i `przyciski.py` (GPIO, usypianie). Poza nimi w repo są skrypty do **kalibracji kamery**, **trenowania modelu** i **testów sprzętu**.

## 2. Architektura

```
                 ┌──────────────────────── Raspberry Pi 5 ────────────────────────┐
 OAK-D S2 ──USB──►  live.py                                                        │
 (RGB 1280×720,  │   ├─ WeighingSession (maszyna stanów)                           │
  głębia 640×400)│   │    ├─ estimate_floor_cm()  ← głębia → wysokość kamery       │
                 │   │    └─ detector.detect_best_pig() ─► YOLOv8n-seg / Otsu     │
 SIGUSR1/2 ──────►   │                                 └─► measure_pig() (PCA)  │
                 │   │                                 └─► estimate_weight()     │
                 │   │                                 └─► WeightSmoother        │
                 │   └─ display.compose_portrait() ──► okno OpenCV 600×1024 ──► Monitor 7″
                 │                                                                 │
                 │  calibration.json  weight_coeff.json  models/pig_seg_best.pt    │
                 │                                                                 │
 Spust GPIO17 ───►  przyciski.py ──SIGUSR1 (start) / SIGUSR2 (przerwij)──► live.py │
 Włącznik GPIO27 ─►   └─ O: ekran off (wlr-randr), rfkill wifi/bt, governor powersave
                 └─────────────────────────────────────────────────────────────────┘

 PC / laptop:  training/*.py  ──► przygotowanie danych i trening YOLO
               check/test.py  ──► test algorytmu na nagraniu
```

### Stos technologiczny

| Warstwa | Technologia |
|---|---|
| Język | Python 3 (type hints, `from __future__ import annotations`) |
| Wizja | OpenCV ≥ 4.10, NumPy |
| Segmentacja | Ultralytics YOLOv8n-seg (≥ 8.4), model `models/pig_seg_best.pt` (6,8 MB, poza gitem) |
| Kamera | Luxonis DepthAI v3 (`depthai ≥ 3.7`) |
| GPIO | `gpiozero` + `lgpio` z apt (systemowy `python3`, nie `.venv`) — tylko `przyciski.py` |
| System | Raspberry Pi OS Bookworm, systemd, X11/Xwayland (`QT_QPA_PLATFORM=xcb`) |

## 3. Struktura repozytorium

| Plik | Rola |
|---|---|
| `live.py` | **Główna aplikacja urządzenia.** Pętla kamery/wideo, maszyna stanów ważenia, sygnały od przycisków, UI. Nie czyta GPIO. |
| `detector.py` | **Rdzeń algorytmu**: segmentacja (YOLO + fallback Otsu), pomiar PCA, wzór na wagę, wygładzanie. Używany przez `live.py` i `check/test.py`. |
| `przyciski.py`, `install_przyciski.sh` | Obsługa spustu i włącznika I/O (jedyny proces czytający GPIO), usługa użytkownika `przyciski`. |
| `display.py` | Rysowanie ekranu 600×1024: obrócony podgląd kamery + pasek statusu. |
| `kalibracja.py` | Jednorazowa kalibracja kamery (wysokość nad podłogą → skala cm/px). |
| `waga.py` | **Starsze podejście** (bez ML): segmentacja świń z samej mapy głębi, waga z objętości. Nie jest używane przez `live.py`. |
| `calibration.json` | Wysokość kamery, ogniskowa, skala cm/px, pole widzenia. |
| `weight_coeff.json` | Współczynniki wzoru na wagę i wybrana metoda. |
| `models/pig_seg/` | Artefakty treningu YOLO (wykresy, `results.csv`, `args.yaml`). Same wagi `*.pt` są w `.gitignore`. |
| `training/extract_frames.py` | Wycinanie klatek z nagrań `dataset/pig_*/rgb_video.mp4`. |
| `training/train_yolo.py` | Podział train/val i trening YOLOv8n-seg na CPU. |
| `check/` | Testy: przyciski (`hello_przyciski.py`), ekran (`hello_screen.py`), algorytm na wideo (`test.py`), instalatory udev OAK-D i przycisku zasilania. |
| `start_live.sh`, `install_autostart.sh`, `pigweight-live.service` | Autostart na Raspberry Pi. |
| `PLAN.md` | Notatka projektowa z przejścia Otsu → YOLO (częściowo nieaktualna). |

## 4. Algorytm pomiaru (`detector.py`)

### 4.1 Segmentacja

1. **YOLOv8n-seg** (`segment_pigs_yolo`) — inferencja z progiem pewności `YOLO_CONF = 0.25`. Każda maska instancji jest skalowana do rozmiaru klatki, binaryzowana progiem 127, z niej brany jest największy kontur, a do pomiaru używana jest maska wypełniona tylko tym konturem. Kontury < `MIN_CONTOUR_AREA_PX = 2000` px są odrzucane. Model ładowany leniwie przy pierwszym wywołaniu.
2. **Fallback Otsu** (`segment_pigs_otsu`) — jeżeli YOLO nic nie znajdzie: skala szarości → blur 11×11 → próg Otsu → domknięcie i otwarcie morfologiczne (elipsa 15×15) → największy jasny obiekt (maska tylko tego obiektu). Działa tylko przy kontraście jasna świnia / ciemne tło.

Pole `source` w wynikach mówi, która metoda zadziałała (`yolo` / `otsu`).

### 4.2 Pomiar wymiarów (PCA) — `measure_pig`

- **Pole** `A [cm²] = pole_konturu [px] × skala²`.
- **Długość i szerokość**: PCA na współrzędnych pikseli maski; `L = 4·√λ₁ × skala`, `W = 4·√λ₂ × skala` (λ — wartości własne macierzy kowariancji; 4σ odpowiada pełnej osi elipsy o jednorodnym wypełnieniu).
- Zwracane są też punkty osi długiej/krótkiej i środek — do rysowania.

### 4.3 Wybór świni

`detect_best_pig` mierzy wszystkie wykryte świnie i wybiera tę, której środek jest **najbliżej środka kadru**. Pozostałe są rysowane cienką linią, ale nie ważone.

### 4.4 Wzór na wagę — `estimate_weight`

| Metoda (`method`) | Wzór | Bieżący współczynnik |
|---|---|---|
| `area` (domyślna, aktywna) | `kg = coeff_area × A` | 0,02173 kg/cm² (świnia 100 kg ≈ 4600 cm² grzbietu) |
| `volume` | `kg = coeff_volume × L × W²` | 0,0003168 |
| `combined` | średnia obu | — |

Współczynniki wyznacza się empirycznie ze świni o znanej wadze: `coeff = waga / pomiar` (pkt 6.2).

### 4.5 Wygładzanie — `WeightSmoother`

Okno ostatnich 30 odczytów. Gdy odchylenie standardowe < 0,5 kg → średnia; w przeciwnym razie odrzucane są wartości dalej niż 2σ od mediany i liczona jest średnia reszty.

## 5. Aplikacja urządzenia (`live.py`)

### 5.1 Tryby uruchomienia

```bash
python live.py
```
Kamera OAK-D S2: RGB 1280×720 (BGR) + głębia 640×400 wyrównana do kamery RGB (preset `ACCURACY`).

```bash
python live.py rgb_video.mp4
```
Plik wideo w pętli, bez głębi — używana jest zapisana skala z `calibration.json`.

### 5.2 Maszyna stanów (`WeighingSession`)

```
 IDLE ──[S / spust]──► CALIBRATING (1 s) ──► MEASURING (3 s) ──► RESULT
   ▲                                                                  │
   └────────────────────────────[S / spust]──────────────────────────┘
```

- **CALIBRATING** — z każdej klatki głębi liczona jest odległość do podłogi (`estimate_floor_cm`: 95. percentyl głębi, potem mediana pikseli w oknie ±5 cm — świnia, będąca bliżej kamery, nie zaburza wyniku). Po 1 s mediana próbek daje nową wysokość `H`, a skala = `H / fx` (fx z fabrycznej kalibracji OAK-D dla 1280×720). Nowa wartość jest **odrzucana**, jeśli wypada poza 50–400 cm lub różni się o > 25% od zapisanej (wtedy trzeba ponownie uruchomić `kalibracja.py`). Poprawna jest zapisywana do `calibration.json` razem z `fx_px` i `ref_width_px = 1280`. Już w tej fazie działa detekcja i wygładzacz.
- **MEASURING** — każda wygładzona waga trafia do listy sesji.
- **Przerwanie** (`SIGUSR2`, włącznik → O) — z każdego stanu powrót do IDLE bez wyniku.
- **RESULT** — statystyki: n, średnia, mediana, min, max, odch. std. Na ekranie wyświetlana jest **średnia**; pełne podsumowanie trafia do konsoli/journala. Wyniki nie są nigdzie zapisywane.

Współczynniki wagi są wczytywane na nowo przy każdym starcie sesji, więc ewentualna edycja `weight_coeff.json` działa bez restartu.

### 5.3 Wejścia

| Wejście | Działanie |
|---|---|
| `S` (klawiatura) lub `SIGUSR1` (spust) | start ważenia |
| `SIGUSR2` (włącznik → O) | przerwanie ważenia, powrót do IDLE |
| `Q` | wyjście |

`live.py` nie czyta GPIO. Handlery sygnałów są ustawiane na samym początku programu (domyślnie `SIGUSR1/2` zabija proces), a sygnały odebrane w trakcie startu są odrzucane.

### 5.4 Przyciski (`przyciski.py`)

| Przycisk | Przewody → pin | Działanie |
|---|---|---|
| Włącznik I/O | żółty → pin 13 (GPIO27), biały → pin 14 (GND) | I = praca; O = uśpienie |
| Spust | pomarańczowy → pin 11 (GPIO17), czarny → pin 9 (GND) | start ważenia |

- `gpiozero`, pull-up, aktywny LOW, filtr drgań 0,1 s (włącznik) / 0,05 s (spust).
- **Spust** wysyła `SIGUSR1` do procesu `python … live.py` tego samego użytkownika (szukany w `/proc`). W pozycji O jest ignorowany. Spust w trakcie ważenia zaczyna je od nowa (jak klawisz `S`).
- **Włącznik → O**: `SIGUSR2` do `live.py`, gaszenie ekranu (`wlr-randr --output … --off`; wyjście wykrywane przy każdym usypianiu, ponawiane co 5 s do 2 min, gdy pulpit jeszcze nie wstał), `sudo rfkill block wifi/bluetooth`, governor CPU `powersave`. **I** przywraca wszystko bez restartu.
- Stan włącznika jest odczytywany przy starcie (start na O od razu usypia).
- `live.py` i kamera pracują dalej podczas uśpienia (tylko ekran zgaszony, CPU zwolniony).
- Instalacja: `bash install_przyciski.sh` — usługa użytkownika `przyciski` (`Restart=always`, linger), uruchamia `przyciski.py` prosto z repo. `start_live.sh` restartuje ją po `git pull`, który zmienił `przyciski.py`.
- Test pinów: `systemctl --user stop przyciski && python3 check/hello_przyciski.py`. Logi: `journalctl --user -u przyciski -f`.

Przycisk zasilania (jeśli nadal podłączony) idzie do złącza **PWR (J2)** Pi 5 — włącza/wyłącza system sprzętowo, bez GPIO (`check/install_power_button.sh` usuwa stary overlay `gpio-shutdown`).

### 5.5 Interfejs (`display.py`)

- Ekran 600×1024 (monitor 1024×600 obrócony w systemie do pionu).
- Górne 914 px: podgląd kamery obrócony o 90° w prawo, skalowany „contain” (bez przycinania), z naniesionymi konturami (zielony = ważona świnia, pomarańczowy = pozostałe), osią długości (czerwona) i szerokości (niebieska).
- Dolny pasek 110 px: **WYS.** (odległość kamery od podłogi z głębi), **WAGA** (kg), status fazy (`kalibr. Ns`, `pomiar Ns`, `brak pomiaru`).
- Zmienne środowiskowe: `PIGWEIGHT_FULLSCREEN=0` wyłącza pełny ekran; `PIGWEIGHT_ROTATE=90|180|270` obraca całe płótno, gdy system zostaje w poziomie.

### 5.6 Start kamery

`wait_for_oak` odpytuje `dai.Device.getAllAvailableDevices()` co 3 s do 180 s (USB po starcie systemu bywa gotowe później). Komunikaty błędów podpowiadają instalację reguł udev (`check/install_oak_udev.sh`, vendor `03e7`).

## 6. Kalibracja

### 6.1 Kamera — `kalibracja.py` (jednorazowo, po montażu)

1. Kamera skierowana pionowo w dół, wypoziomowana, w kadrze pusta podłoga.
2. Pobiera `fx` z kalibracji fabrycznej dla 1920×1080, odrzuca 10 klatek rozgrzewki, bierze medianę głębi z okna 40×40 px na środku.
3. Zapisuje `calibration.json`:

```json
{ "height_cm": 131.1, "fx_px": 1454.47, "scale_cm_per_px": 0.090136,
  "px_per_cm": 11.09, "fov_width_cm": 173.1, "fov_height_cm": 97.3 }
```

`ref_width_px` mówi, dla jakiej szerokości obrazu obowiązuje `scale_cm_per_px`. Dla obrazu o innej rozdzielczości (ten sam kadr) skalę przelicza `detector.scale_for_width(cal, szerokość)`: `scale × ref_width_px / szerokość`. Brak pola = 1920. Korzystają z tego `check/test.py`, `waga.py` i `live.py` w trybie wideo.

Przy 131 cm kamera widzi ok. 173 × 97 cm podłogi, 1 px ≈ 0,9 mm (przy 1920 px szerokości).

`live.py` dodatkowo rekalibruje wysokość automatycznie przed każdym ważeniem (pkt 5.2).

### 6.2 Waga — stałe współczynniki

Współczynniki w `weight_coeff.json` zostały ustalone wcześniej w aplikacji webowej (2026-05-11) na świni o znanej wadze i są używane bez zmian: metoda `area`, `coeff_area = 0,02173165`, `coeff_volume = 0,0003168`. `live.py` tylko je czyta.

Gdyby kiedyś trzeba je było zmienić: `coeff_area = znana_waga / A`, gdzie `A` to pole wypisywane przez `live.py` w konsoli (`A=…cm2`), i wpisać wynik do `weight_coeff.json`.

## 7. Model ML i trening

| Parametr | Wartość |
|---|---|
| Architektura | YOLOv8n-seg (nano, segmentacja instancji), 1 klasa: `pig` |
| Dane | klatki z nagrań OAK-D (`extract_frames.py`, co 15. klatka ≈ 1/s przy 15 FPS), oznaczone poligonami w Roboflow, eksport YOLOv8 |
| Podział | 85% train / 15% val (`VAL_RATIO = 0.15`, seed 42) |
| Trening | 80 epok, imgsz 640, batch 4, CPU, early stopping 20, optymalizator auto, lr0 0,01 |
| Wynik (najlepsza epoka 48, maski) | precision 0,96 · recall 0,89 · mAP50 0,89 · mAP50-95 0,84 |
| Wynik (epoka 80, maski) | precision 0,99 · recall 0,86 · mAP50 0,89 · mAP50-95 0,83 |

`train_yolo.py` kopiuje `best.pt` do `training/models/pig_seg_best.pt`; na urządzenie trzeba go ręcznie skopiować do `models/pig_seg_best.pt` (np. `scp`), bo wagi nie są w gicie.

## 8. Wdrożenie na Raspberry Pi

1. Sklonować repo (np. `~/Desktop/pigweight`), utworzyć `.venv`, `pip install -r requirements.txt`.
2. Skopiować `models/pig_seg_best.pt`.
3. Uruchomić `./check/install_oak_udev.sh`, odłączyć i podłączyć kamerę.
4. Opcjonalnie `./check/install_power_button.sh`.
5. Uruchomić `./install_autostart.sh` i `bash install_przyciski.sh`, a potem `sudo reboot`.

`install_autostart.sh` instaluje usługę **systemd** `pigweight-live` (z podstawionymi ścieżkami i użytkownikiem, `Restart=on-failure`, `RestartSec=15`) oraz zapasowy wpis `~/.config/autostart/pigweight-live.desktop`.

`start_live.sh` przy każdym starcie:
1. loguje do `live_autostart.log`,
2. robi **`git pull --ff-only`** (automatyczna aktualizacja kodu; brak sieci nie blokuje startu),
3. wybiera Pythona z `.venv` / `venv` / systemowego,
4. przy `PIGWEIGHT_BOOT_DELAY=1` czeka 20 s, a następnie do 40×3 s na pojawienie się OAK-D w `lsusb`,
5. ostrzega o braku reguł udev / modelu i uruchamia `live.py` przez `exec`.

Logi: `tail -f live_autostart.log`, `journalctl -u pigweight-live -f`.

## 9. Założenia i ograniczenia

- Kamera musi być **prostopadła do podłogi** i nieruchoma; skala jest jedna dla całego kadru (brak korekcji perspektywy i dystorsji obiektywu).
- Skala liczona jest dla **poziomu podłogi**, a grzbiet świni jest 50–70 cm wyżej, więc piksel na grzbiecie odpowiada mniejszej odległości. Ten systematyczny błąd jest „wchłaniany” przez współczynnik kalibracyjny — działa tylko przy podobnej wysokości kamery i podobnym rozmiarze świń jak podczas kalibracji.
- Waga zależy liniowo od pola rzutu z góry; pozycja świni (leżąca, zgięta, z opuszczoną głową) zmienia wynik.
- Ważona jest jedna świnia — najbliższa środka kadru.
- Brak zapisu historii ważeń, identyfikacji zwierząt (RFID/kolczyk) i eksportu danych.
- Inferencja YOLO idzie na CPU Pi 5 dla każdej klatki 1280×720 (VPU kamery nie jest wykorzystywane).

## 10. Zauważone niespójności i ryzyka

### Poprawione (2026-10-18)

1. **Skala zależna od rozdzielczości.** `calibration.json` ma pole `ref_width_px`, a wszystkie miejsca liczą skalę przez `scale_for_width()`. Wcześniej po pracy `live.py` (1280×720) zdjęcia i nagrania 1920×1080 dostawały pole zawyżone ~2,25×. Sprawdzone: ta sama klatka w 1920 i 1280 px daje 4382 vs 4369 cm² (95,2 vs 94,9 kg).
2. **`waga.py` nie nadpisuje już współczynników** `detector.py` — zapisuje własny klucz `coeff_depth_volume` i zachowuje resztę pliku (stary klucz `coeff` jest nadal czytany).
3. **Pomiar PCA z jednej świni** — maska budowana z wybranego konturu (Otsu i YOLO).
4. Usunięta aplikacja webowa (`app.py`, `index.html`) i jej zależności (FastAPI, Uvicorn) — urządzenie korzysta tylko z `live.py`. Tym samym znika problem braku uwierzytelniania.
5. `kalibracja.py` zapisuje `calibration.json` obok skryptu, niezależnie od katalogu roboczego.
6. `requirements.txt`: instrukcje dla Linux/Pi; poprawiony docstring `train_yolo.py` (85/15).

### Nowe przyciski (2026-11-17)

7. Stary przycisk na GPIO 12 (pin 32, Blinka) usunięty. Spust (GPIO17) i włącznik I/O (GPIO27) obsługuje `przyciski.py`, który steruje `live.py` sygnałami. Wcześniejsza wersja uruchamiała przy każdym spuście nowy program pomiaru — przy działającym `live.py` dałoby to konflikt o kamerę OAK-D.

### Otwarte

1. Automatyczny `git pull` przy starcie oznacza, że każdy push na gałąź wdrożeniową trafia na urządzenie przy następnym uruchomieniu, bez testów.
2. Współczynniki wagi są stałe (z dawnej kalibracji webowej) — `live.py` nie ma trybu ich kalibracji (pkt 6.2).
3. Etykieta „WYS.” na ekranie to wysokość **kamery nad podłogą**, nie wysokość świni.
4. `PLAN.md` opisuje nieistniejące `models/best.pt`.
5. Uśpienie (O) wyłącza Wi-Fi — znika SSH, a `git pull` przy starcie na O nie zadziała.
6. `przyciski.py` wymaga sudo bez hasła (rfkill, governor); bez niego usypia tylko ekran.

## 11. Historia rozwoju (z gita)

- **2026-07-12** — import prototypów „Podejście 1–3”: Otsu + PCA → głębia (`waga.py`) → YOLOv8-seg.
- **2026-07-18** — wyświetlacz, przycisk, autostart, podgląd wysokości.
- **2026-08-01** — zmiana pinów, przycisk zasilania na PWR.
- **2026-10-03** — refaktoryzacja repo, przejście na monitor 7″ w pionie (`display.py`), poprawki autostartu.
- **2026-11-17** — nowe przyciski: spust i włącznik I/O (`przyciski.py`).

Cel metryk z `PLAN.md`: błąd < 5% dla pojedynczej świni, < 8% dla dwóch stykających się, detekcja < 100 ms na klatkę.
