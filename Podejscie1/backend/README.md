# WagaDlaŚwiń — backend

FastAPI + YOLOv8-seg (ONNX) + OpenCV + XGBoost. Realizuje 3-etapową hybrydę:

```
zdjęcie -> YOLOv8-seg -> maska -> cechy OpenCV -> XGBoost -> kg
```

## Struktura

```
backend/
├── app/
│   ├── __init__.py
│   ├── main.py        # FastAPI: /healthz, /predict, /calibrate
│   ├── yolo.py        # ładowanie ONNX + segmentacja
│   ├── features.py    # cechy z maski (area, PCA, hu, profil szerokości)
│   └── xgb.py         # ładowanie XGBoost + predykcja + bias
├── models/
│   ├── pig-detector.onnx  # YOLOv8-seg (z training/runs/segment/.../best.onnx)
│   ├── pig_weight.json    # XGBoost (z training/runs/xgb/pig_weight.json)
│   └── calibration.json   # opcjonalnie: bias_kg per chlewnia
├── requirements.txt
└── README.md
```

## Setup (lokalnie / dev)

```powershell
# z katalogu backend/
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# Skopiuj modele:
mkdir models
copy ..\web\public\models\pig-detector.onnx models\pig-detector.onnx
# pig_weight.json — po wytrenowaniu:
#   python ../training/train_xgboost.py --copy-to-backend
```

Uruchomienie serwera:

```powershell
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Sprawdzenie:

```powershell
curl http://localhost:8000/healthz
```

## Setup na Raspberry Pi 5

```bash
sudo apt update
sudo apt install -y python3-venv libgl1 libglib2.0-0
cd ~/waga-dla-swin/backend
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

Uruchomienie jako serwis systemowy (`/etc/systemd/system/waga-backend.service`):

```ini
[Unit]
Description=WagaDlaSwin backend
After=network.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/waga-dla-swin/backend
ExecStart=/home/pi/waga-dla-swin/backend/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now waga-backend
sudo systemctl status waga-backend
```

## Zmienne środowiskowe

| Zmienna | Domyślnie | Znaczenie |
|---------|-----------|-----------|
| `WAGA_MODELS_DIR` | `<backend>/models` | Katalog z plikami modeli |

## Endpoints

### `GET /healthz`

```json
{ "ok": true, "hasYolo": true, "hasXgb": true, "version": "0.1.0", "biasKg": 0.0 }
```

### `POST /predict`

`multipart/form-data`:
- `image` — JPEG/PNG kadru z kamery
- `target_min_kg`, `target_max_kg` — progi normy
- `margin_thin_kg`, `margin_fat_kg` — marginesy werdyktu
- `confidence_threshold` — próg score YOLO (domyślnie 0.25)
- `px_per_cm`, `camera_height_cm` — kalibracja skali (z UI)

Odpowiedź: patrz `PredictResponse` w `app/main.py`.

### `POST /calibrate`

Dostraja bias modelu — `mass_kg` (znana waga z legalnej wagi w chlewni)
+ `image` świni. Zapisuje `calibration.json`.

## Szybki test

Po wytrenowaniu modeli wrzuć dowolne zdjęcie:

```powershell
curl -F image=@..\training\datasets\PigRGB-Weight\RGB_MASK_3394\RGB_3394\100.9_14\100.9kg_1.png ^
     -F target_min_kg=90 -F target_max_kg=110 ^
     http://localhost:8000/predict
```
