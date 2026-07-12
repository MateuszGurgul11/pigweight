# Plan poprawek — WagaDlaŚwiń

Wynik analizy kodu względem założeń projektu (zamysl.md + spec.md).
Poprawki pogrupowane wg priorytetu: **Krytyczne → Ważne → Nice-to-have**.

---

## Krytyczne (blokują poprawne działanie)

### P1 — Licznik FPS jest zepsuty
**Plik:** `web/src/components/CameraView.tsx` linia 193–209

`setInterval` co 100 ms inkrementuje `frames += 1` — zawsze dostaje 1 ticka między dwoma pomiarami, więc zawsze pokazuje ~2 fps niezależnie od rzeczywistości. Zamiast tego FPS powinien być liczony w pętli RAF (inkrementacja `rafFrame` na każdy `requestAnimationFrame`, odczyt co 500 ms).

**Naprawa:** przenieś licznik klatek do pętli RAF, usuń `setInterval`.

---

### P2 — Race condition: nakładające się wywołania ONNX w CameraView
**Plik:** `web/src/components/CameraView.tsx` linia 150–168

`void (async () => { ... })()` jest wywoływane co N klatek RAF bez sprawdzenia, czy poprzednie wywołanie ONNX skończyło działać. Na słabym sprzęcie (Raspberry Pi, tani telefon) wywołania się nakładają i wyniki przylatują w losowej kolejności.

**Naprawa:** dodaj flagę `inferenceRunning = useRef(false)` — jeśli `true`, pomijaj frame i nie startuj nowego wywołania.

---

### P3 — `runMockDetection` zwraca `areaPx: 0`
**Plik:** `web/src/lib/detection.ts` linia 59

```ts
return { bbox, areaPx: 0, source: 'bbox' }
```

W `CameraView` przy trybie `mock` powierzchnia jest liczona osobno z bbox (`bboxAreaPx`), ale wyeksponowane pole `areaPx` w obiekcie `Detection` wynosi 0. To nie blokuje wyświetlania masy, ale jest mylące i powoduje, że `detection.areaPx` jest bezużyteczne w trybie symulacji.

**Naprawa:** oblicz `areaPx` wewnątrz `runMockDetection` tak samo jak w CameraView.

---

### P4 — Duplikacja `drawMaskOverlay` w dwóch komponentach
**Pliki:** `web/src/components/CameraView.tsx` linia 32–52 i `web/src/components/TestView.tsx` linia 36–59

Identyczna funkcja skopiowana w dwóch miejscach. Każda kopia tworzy osobny `maskCanvas` na poziomie modułu — przy jednoczesnym renderowaniu obu mogą się wzajemnie nadpisywać.

**Naprawa:** wydziel do `web/src/lib/drawOverlay.ts`, importuj w obu komponentach.

---

## Ważne (wpływają na dokładność lub użyteczność)

### P5 — Model estymacji masy ignoruje proporcje sylwetki
**Plik:** `web/src/lib/heuristic.ts` linia 18–31

Aktualny wzór: `masa ∝ area^1.5` używa tylko powierzchni rzutu. Dla świni w widoku z góry stosunek długość/szerokość (aspect ratio) niesie informację o kondycji — chuda świnia jest węższa przy tej samej długości. PCA z `dimensions.ts` już wyznacza `lengthPx` i `widthPx`, ale te dane nie są przekazywane do `estimateMassKg`.

**Naprawa:** rozszerz `estimateMassKg` o opcjonalny parametr `dims: MaskDimensions | null`. Gdy dims dostępne, użyj wzoru dwucechowego:
```
masa ≈ calibration * area^1.2 * (length/width)^0.3
```
Wykładniki do kalibracji empirycznej; domyślnie zostaw `area^1.5` gdy brak dims (backward compat).

---

### P6 — Błąd skalowania PCA w `analyzeMask`
**Plik:** `web/src/lib/dimensions.ts` linia 95–101

```ts
const avgScale = (scaleX + scaleY) / 2
const lengthPx = lengthLocalPx * avgScale
const widthPx  = widthLocalPx  * avgScale
```

Obie osie PCA skalowane tą samą *średnią* skalą X/Y. Jeśli kamera daje obraz nieizotropowy (pixel aspect ratio ≠ 1, lub różna rozdzielczość H/V po letterboxie), długość i szerokość będą przekłamane. Poprawne podejście: rozbij `lengthLocalPx` i `widthLocalPx` na składowe wektora własnego i przeskaluj każdą składową osobno.

**Naprawa:**
```ts
const cos = Math.cos(angle)
const sin = Math.sin(angle)
const lengthPx = 4 * Math.sqrt(lambdaMax) * Math.sqrt((cos*scaleX)**2 + (sin*scaleY)**2)
const widthPx  = 4 * Math.sqrt(lambdaMin) * Math.sqrt((sin*scaleX)**2 + (cos*scaleY)**2)
```

---

### P7 — Brak blokady ekranu (WakeLock API)
**Plik:** `web/src/components/CameraView.tsx`

Farmer chodzi po chlewni — ekran telefonu/tabletu gaśnie po 30–60 s. Aplikacja traci kamerę i wynik.

**Naprawa:** dodaj `navigator.wakeLock.request('screen')` przy uruchamianiu kamery. Obsłuż zwolnienie przy `visibilitychange` i ponowne pobranie przy powrocie (przeglądarki mobilne zwalniają lock gdy zakładka schodzi w tło).

```ts
useEffect(() => {
  let lock: WakeLockSentinel | null = null
  const acquire = async () => {
    try { lock = await navigator.wakeLock?.request('screen') } catch {}
  }
  const onVisible = () => { if (document.visibilityState === 'visible') void acquire() }
  void acquire()
  document.addEventListener('visibilitychange', onVisible)
  return () => {
    document.removeEventListener('visibilitychange', onVisible)
    lock?.release()
  }
}, [])
```

---

### P8 — Dashboard wyświetla werdykty po angielsku
**Plik:** `web/src/pages/Dashboard.tsx` linia 131

```tsx
{r.massKg.toFixed(1)} kg · {r.verdict}
```
Wyświetla `thin`, `ok`, `fat` zamiast polskich etykiet.

**Naprawa:** użyj `verdictLabel(r.verdict)` z `lib/heuristic.ts`.

---

### P9 — Domyślne zakresy mas niezgodne z założeniami projektu
**Plik:** `web/src/lib/settings.ts` linia 32–35

Domyślne `targetMinKg: 100, targetMaxKg: 120` → przedział normy 100–120 kg.
Założenia projektu (zamysl.md) mówią o klasyfikacji: za chuda (<90 kg), OK (90–110 kg), za gruba (>110 kg).

**Naprawa:**
```ts
targetMinKg: 90,
targetMaxKg: 110,
marginThinKg: 0,
marginFatKg: 0,
```
(marginesy 0 → za chuda jeśli <90, za gruba jeśli >110 — proste progi bez bufora).

---

### P10 — `loadSettings` bez walidacji schematu
**Plik:** `web/src/lib/settings.ts` linia 48–56

```ts
const parsed = JSON.parse(raw) as Partial<UserSettings>
return { ...DEFAULT_SETTINGS, ...parsed }
```

Jeśli użytkownik miał starszą wersję ustawień z inną nazwą klucza lub złym typem (`"pxPerCm": "abc"`), wartość przejdzie bez walidacji i trafi jako string do `estimateMassKg`, powodując `NaN`.

**Naprawa:** po sparsowaniu przefiltruj wartości:
```ts
const sanitize = (p: Partial<UserSettings>): Partial<UserSettings> => ({
  ...('targetMinKg' in p && Number.isFinite(p.targetMinKg) ? { targetMinKg: p.targetMinKg } : {}),
  // ... dla każdego pola z Number.isFinite / typeof checks
})
```
Lub użyj Zod (już w zależnościach?) do parsowania schematu.

---

### P11 — `bestAnchor` — brak NMS, tylko 1 detekcja
**Plik:** `web/src/lib/detection.ts` linia 140–159

Dla chlewni z wieloma świniami w kadrze, `bestAnchor` bierze tylko jeden anchor (najwyższy score). Pozostałe świnie są ignorowane. W realistycznym scenariuszu farmer skanuje jedną świnię na raz, ale gdy dwie są blisko kadru, wynik może skakać między nimi.

**Naprawa (MVP):** dodaj prosty NMS i zwróć listę `Detection[]` posortowaną po score. W `CameraView` wizualizuj wszystkie detekcje, ale miarę szacuj dla największej (lub najbliższej centrum kadru). Pełne multi-pig to etap post-MVP.

---

## Nice-to-have (UX / stabilność)

### P12 — Brak feedbacku po kliknięciu „Zapisz pomiar"
**Plik:** `web/src/components/CameraView.tsx` linia 384–392

Przycisk nie daje żadnego sygnału że zapis się udał (toast, zmiana koloru, wibracja).

**Naprawa:** po `persistMeasurement` pokaż przez 1.5 s tekst „Zapisano ✓" na przycisku. Opcjonalnie `navigator.vibrate(100)` dla haptyki.

---

### P13 — Stale closure na `display` w pętli RAF w TestView
**Plik:** `web/src/components/TestView.tsx` linia 256–257

```ts
} else {
  drawCanvas(video, display?.detection ?? null)
}
```
`display` pochodzi z zamknięcia useEffect, który ma pustą tablicę zależności + eslint-disable. Gdy między klatkami nadejdzie nowy wynik, klatki bez inferencji rysują stary wynik (drobne przesunięcia bbox przy pauzie).

**Naprawa:** przenieś ostatni znany `Detection` do `useRef` zamiast czytać ze stanu (analogicznie jak `currentRef` w CameraView).

---

### P14 — Brak trybu portrait-lock / orientacji
**Plik:** `web/src/main.tsx` / `index.html` / manifest

Farmer trzyma telefon pionowo, ale obrót powoduje przełączenie widoku i momentalne odłączenie kamery.

**Naprawa:** w `manifest.webmanifest` ustaw `"orientation": "portrait"`. Dla przeglądarek bez PWA: `screen.orientation?.lock('portrait').catch(() => undefined)`.

---

### P15 — Brak audio/haptyki dla werdyktu
Użytkownik w jednej ręce trzyma telefon, w drugiej spray. Musi zerkać na ekran zamiast słyszeć sygnał.

**Naprawa:** dodaj opcjonalny (przełącznik w ustawieniach) dźwięk/wibrację różny dla każdego werdyktu:
- `ok` → krótkie wibrowanie (200 ms)
- `fat` / `thin` → podwójne wibrowanie (200–100–200 ms)
- Dźwięk: prosty syntetyczny beep przez `AudioContext`.

---

### P16 — `resetOnnxSessionCache` nigdzie nie jest wywoływane
**Plik:** `web/src/lib/detection.ts` linia 385–387

Jeśli ładowanie modelu się nie powiedzie (brak pliku), `sessionPromise` jest `null` na stałe. Nie ma mechanizmu ponownej próby po np. pojawieniu się pliku lub zmianie ustawień.

**Naprawa:** w `CameraView` przy każdej zmianie `settings.detectionMode` na `'onnx'` wywołuj `resetOnnxSessionCache()` przed `preloadOnnxSession()`.

---

## Podsumowanie — kolejność implementacji

| # | Priorytet | Szacowany czas | Plik(i) |
|---|-----------|---------------|---------|
| P1 | Krytyczny | 30 min | CameraView.tsx |
| P2 | Krytyczny | 20 min | CameraView.tsx |
| P3 | Krytyczny | 5 min | detection.ts |
| P4 | Krytyczny | 30 min | CameraView.tsx, TestView.tsx → drawOverlay.ts |
| P7 | Ważny | 20 min | CameraView.tsx |
| P8 | Ważny | 5 min | Dashboard.tsx |
| P9 | Ważny | 5 min | settings.ts |
| P10 | Ważny | 30 min | settings.ts |
| P5 | Ważny | 1 h | heuristic.ts |
| P6 | Ważny | 30 min | dimensions.ts |
| P11 | Ważny | 2 h | detection.ts |
| P12 | Nice | 20 min | CameraView.tsx |
| P13 | Nice | 15 min | TestView.tsx |
| P14 | Nice | 10 min | manifest / main.tsx |
| P15 | Nice | 45 min | CameraView.tsx + ustawienia |
| P16 | Nice | 15 min | CameraView.tsx |




cd "/Users/ziomson/Desktop/Praca/Waga Świń"
git remote add origin https://github.com/Mateuszgurgul11/pigweight.git
git push -u origin master