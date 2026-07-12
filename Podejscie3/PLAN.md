# Podejscie3 — Plan ulepszonej detekcji swini

## Baza
Kopia Podejscie2 (prosta segmentacja Otsu + PCA + wzor empiryczny na wage).
Dziala dobrze dla pojedynczej swini o wyraznym kontraście tlo/swiania.

## Problem do rozwiazania
- Dwie stykajace sie swinie → jeden duzy kontur → przeszacowanie wagi (~35% blad)
- Slabe swiatlo lub jasna podloga → Otsu zawodzi, brak detekcji
- Brak pewnosci co do dokladnego obrysu swini (glowa/ogon moga byc uciete)

## Podejscie — model segmentacji instancji

### Opcja A: YOLOv8-seg (rekomendowana)
- Model: `yolov8n-seg` lub `yolov8s-seg` (Ultralytics)
- Trening na wlasnych danych oznaczonych w Roboflow
- Wyjscie: maska binarna per-instancja → do measure_pig() tak jak dotychczas
- Zalety: dziala na CPU w ~50ms/klatke, latwy eksport do ONNX

### Opcja B: SAM (Segment Anything Model)
- Meta AI, zero-shot — nie wymaga treningu
- Wolny (~500ms/klatke na CPU), wymaga promptu (punkt lub bbox)
- Dobry do szybkiego testowania bez zbierania danych

### Opcja C: Mask R-CNN (torchvision)
- Pretrenowany na COCO, fine-tuning na swinach
- Ciezszy od YOLO, ale dobrze udokumentowany

## Kroki implementacji (Opcja A — YOLOv8-seg)

### 1. Zbieranie i oznaczanie danych (Roboflow)
- Wyeksportuj klatki z rgb_video.mp4 co ~30 klatek (~20-50 obrazow na video)
- Zaladuj do projektu Roboflow (typ: Instance Segmentation)
- Oznacz kazda swinie osobno — polygon tool
- Minimum: ~200 oznaczonych swin (mozna augmentowac x3-5 w Roboflow)
- Export: YOLOv8 format

### 2. Trening
```bash
pip install ultralytics
yolo train model=yolov8n-seg.pt data=dataset.yaml epochs=100 imgsz=640
```

### 3. Integracja w detector.py
```python
from ultralytics import YOLO
model = YOLO("best.pt")

def segment_pigs_yolo(image):
    results = model(image, verbose=False)[0]
    pigs = []
    if results.masks is None:
        return pigs
    for mask_data in results.masks.data:
        mask = (mask_data.cpu().numpy() * 255).astype(np.uint8)
        mask = cv2.resize(mask, (image.shape[1], image.shape[0]))
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if contours:
            cnt = max(contours, key=cv2.contourArea)
            pigs.append((cnt, mask))
    return pigs
```

### 4. Pomiary
Uzywamy tej samej funkcji `measure_pig()` — maska z YOLO zamiast Otsu.

## Struktura plikow Podejscie3
```
Podejscie3/
  app.py          — web interface (jak Podejscie2, + endpoint /reload_model)
  live.py         — kamera live (jak Podejscie2, + YOLO)
  test.py         — test na video (jak Podejscie2, + YOLO)
  detector.py     — NEW: segment_pigs_yolo() + segment_pig_otsu() jako fallback
  calibration.json
  weight_coeff.json
  models/
    best.pt       — wytrenowany model YOLOv8-seg
  PLAN.md         — ten plik
```

## Metryki sukcesu
- Blad wagi dla pojedynczej swini: < 5% (obecny ~3-5%)
- Blad dla 2 stykajacych sie swin: < 8% (obecny ~35%)
- Czas detekcji na klatce 1920x1080: < 100ms
