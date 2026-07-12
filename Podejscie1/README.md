# WagaDlaŚwiń

Szacunek masy świni z widoku kamery z góry (PWA). Zobacz [`zamysl.md`](zamysl.md), specyfikację [`spec.md`](spec.md).

## Szybki start

```bash
cd web
npm install
npm run dev
```

## Szybki start — model

1. **Eksport** z Roboflow: format **YOLOv8** (najlepiej **Segmentation**), rozpakuj do `roboflow/`.
2. **Przygotuj zbiór i wytrenuj**:

```bash
cd training
pip install -r requirements.txt
python scripts/prepare_dataset.py            # robi train/val ze zbioru z Roboflow
python train_yolo_seg.py --copy-to-web       # trening + eksport ONNX prosto do aplikacji
```

3. W aplikacji webowej (`web/`) wybierz w `Ustawieniach` tryb **Model ONNX** i skalibruj
   współczynnik na kilku świniach o znanej masie (świń trzymanych przy stałej wysokości kamery).

## Struktura

| Ścieżka | Opis |
|---------|------|
| `web/` | Aplikacja Vite + React (kamera, heurystyka, PWA, raport) |
| `training/` | Instrukcja i szablon treningu YOLO |
| `supabase/migrations/` | SQL dla tabeli pomiarów |
| `video/` | (Opcjonalnie, lokalnie) surowe nagrania pionowe — patrz `training/README.md` |

Folder `video/` jest w `.gitignore`, żeby przypadkowo nie wrzucać dużych plików do repozytorium.

## Dokumentacja techniczna

- [`web/README.md`](web/README.md) — zmienne środowiskowe i build.
