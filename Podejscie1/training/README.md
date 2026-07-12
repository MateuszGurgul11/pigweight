# Trening modelu świń (widok z góry)

## Szybka ścieżka segmentacji (zalecane)

Jeśli masz w repo katalog `roboflow/` z eksportem **YOLOv8 Segmentation** (klasa `Pig-weight` / `pig`):

```bash
cd training
pip install -r requirements.txt
python scripts/prepare_dataset.py            # roboflow/ -> datasets/pig_top/{train,val}
python train_yolo_seg.py --copy-to-web       # trenuje + eksportuje ONNX do web/public/models/
```

Po treningu w aplikacji w `Ustawieniach` ustaw tryb **Model ONNX**. Aplikacja sama wykryje, że
to model segmentacji i użyje **powierzchni maski** (zamiast prostokąta) do szacunku masy.

Najczęstsze opcje:

```bash
python train_yolo_seg.py --epochs 200 --batch 8 --weights yolov8s-seg.pt --device 0
```

Parametry treningu:

- `yolov8n-seg.pt` (domyślnie) — najszybciej, mniejsza dokładność.
- `yolov8s-seg.pt` — lepsza dokładność, wolniej (zalecane jeśli masz GPU).
- `--device 0` — GPU; pomiń, jeśli trenujesz na CPU.
- `--epochs` — 100-200 wystarczy; skrypt ma `patience=30`, więc zatrzyma się gdy przestanie się poprawiać.

---

## Manualne (od zera)


## 1. Zbieranie danych

- Nagraj zdjęcia / klatki z **kamery z góry** w realnych warunkach (światło, błoto, wiele zwierząt w kadrze).
- Im większa różnorodność, tym lepsza generalizacja.

### Nagrania pionowe w folderze `video/`

Jeśli masz gotowe filmy (pionowe, kamera skierowana w dół — jak w docelowej aplikacji), umieść je w **`video/`** w katalogu głównym repozytorium (obok `training/`, `web/`). Ten folder możesz trzymać tylko lokalnie — duże pliki zwykle nie trafiają do Gita.

Wycięcie klatek do etykietowania (z katalogu `training/`):

```bash
pip install -r requirements.txt
python scripts/extract_frames.py --every 15
```

Opcje:

- `--input /ścieżka/do/folderu` — jeśli filmy są gdzie indziej,
- `--every 30` — rzadsze klatki (mniej powtórzeń, szybsze oznaczanie),
- `--max-per-video 200` — górny limit klatek z jednego filmu.

Obrazy trafią do `training/datasets/pig_top/images/train/`. Potem w Roboflow/CVAT narysuj bboxy i wyeksportuj etykiety **YOLOv8** — w repozytorium musisz mieć parę:

- `datasets/pig_top/images/train/nazwa.jpg`
- `datasets/pig_top/labels/train/nazwa.txt` (współrzędne bbox w formacie YOLO)

Plik [`datasets/pig_top/data.yaml`](datasets/pig_top/data.yaml) jest już ustawiony pod ten układ. **Bez plików `.txt` trening się nie uruchomi** — skrypt sprawdzi to przed startem.

## 2. Etykietowanie

- **Roboflow**, **CVAT** lub **Label Studio**: bounding box wokół każdej świny w kadrze (jedna klasa, np. `pig`).
- Eksport w formacie **YOLOv8** (foldery `images` + `labels`).

### Roboflow — co zrobić po eksporcie zip

1. W projekcie Roboflow: **Generate** → **Download Dataset** → format **YOLOv8**.
2. Rozpakuj zip — zwykle masz `train/images`, `train/labels` (czasem tylko `images` / `labels` w głównym folderze).
3. **Skopiuj** zawartość:
   - wszystkie `.jpg` z `train/images/` → `training/datasets/pig_top/images/train/` (jeśli już tam są Twoje klatki, możesz **nadpisać** tylko etykiety — ważne, żeby **nazwy plików** `.jpg` i `.txt` były **identyczne** z tym, co w Roboflow),
   - wszystkie `.txt` z `train/labels/` → `training/datasets/pig_top/labels/train/`.
4. Sprawdź pary:

```bash
cd training
python scripts/check_labels.py
```

Dopiero gdy skrypt napisze **„OK — każdy obraz ma etykietę”**, uruchom `python train_yolo.py`.

## 3. Fine-tuning (Ultralytics)

Wymagania: Python 3.10+, `pip install ultralytics`.

```bash
cd training
pip install ultralytics
python train_yolo.py
```

Skrypt zakłada strukturę `datasets/pig_top/` z plikiem `data.yaml` — dostosuj ścieżki do swojego zbioru.

## 4. Eksport do przeglądarki

Po treningu:

```python
from ultralytics import YOLO
model = YOLO("runs/detect/train/weights/best.pt")
model.export(format="onnx", imgsz=640, simplify=True)
```

Skopiuj wygenerowany plik ONNX do `web/public/models/pig-detector.onnx` i w aplikacji wybierz tryb **Model ONNX**.

## Dokumentacja

- [Ultralytics YOLO](https://docs.ultralytics.com/)
- [ONNX Runtime Web](https://onnxruntime.ai/docs/tutorials/web/)
