# Specyfikacja produktu — WagaDlaŚwiń (MVP)

## 1. Cel

Aplikacja szacuje **masę świni** na podstawie widoku z kamery skierowanej **pionowo w dół** i klasyfikuje zwierzę jako **za chude**, **w normie** lub **za grube** względem ustawionego przez użytkownika przedziału docelowej masy.

## 2. Wyjście (ekran główny)

| Element | Opis |
|--------|------|
| **Szacowana masa** | Liczba w **kg** (jedna wartość punktowa), z dopiskiem że jest to **szacunek**, nie pomiar wagą branżową. |
| **Przedział raportowany** | Opcjonalnie wyświetlany **margines** (np. ±X kg) wynikający z niepewności modelu/heurystyki — domyślnie można ukryć w MVP. |
| **Werdykt** | Jedna z trzech etykiet: **Za chuda** / **W normie** / **Za gruba** (kolorystyka: niebieski / zielony / pomarańczowy lub czerwony). |
| **FPS / status** | Wskaźnik działania kamery i inferencji (opcjonalnie w trybie deweloperskim). |

Użytkownik może **zatrzymać** ostatni wynik na ekranie (np. przy oznaczaniu sprayem), aby nie znikał przy ruchu.

## 3. Ustawienia (minimalny zestaw MVP)

| Parametr | Typ | Znaczenie |
|----------|-----|-----------|
| **Masa docelowa — od** | liczba (kg) | Dolna granica „normy” |
| **Masa docelowa — do** | liczba (kg) | Górna granica „normy” |
| **Odstęp „za chuda”** | liczba (kg) | Poniżej `od - odstęp` → za chuda |
| **Odstęp „za gruba”** | liczba (kg) | Powyżej `do + odstęp` → za gruba |
| **Kalibracja skali** | liczba dodatnia (współczynnik) | Skalowanie mapowania rozmiaru w pikselach → kg (zależne od wysokości kamery) |
| **Próg powierzchni min.** | piksele² (opcjonalnie) | Ignorować detekcje mniejsze niż próg (szum) |

**Logika progów (przykład):**

- `estimated_kg < target_min - margin_thin` → **Za chuda**
- `estimated_kg > target_max + margin_fat` → **Za gruba**
- w przeciwnym razie → **W normie**

Wartości domyślne można ustawić np. `od=100`, `do=120`, marginesy `10` kg.

## 4. Wejście techniczne

- Strumień wideo z kamery (`getUserMedia`), preferowany tył urządzenia jeśli dostępny.
- Wynik detekcji: **bounding box** (lub maska — faza późniejsza); z bbox liczona jest **powierzchnia** (px²) jako proxy masy.

## 5. Poza zakresem MVP

- Zapis wideo na serwerze bez zgody.
- Certyfikacja urzędowa pomiaru masy.

## 6. Zgodność z [zamysl.md](zamysl.md)

Specyfikacja realizuje punkt 1 (wymiary w czasie rzeczywistym, szacunek wagi w przedziale, ocena chuda/OK/gruba, ustawienia) oraz przygotowuje pod rozszerzenie o dashboard (osobny dokument / moduł).
