# Depth Bridge — kontrakt WebSocket między płytką a PWA (Faza 2)

## Cel

Architektura docelowa waży świnie w następujący sposób:

```
[ RealSense USB ] → [ SBC: RPi 5 / Jetson ] → (Wi-Fi) → [ PWA na telefonie ]
```

Płytka jest tylko „głupim" routerem danych: czyta aligned depth+color z
RealSense (przez librealsense / pyrealsense2) i wypycha surowe klatki do
telefonu. Cała analiza (ONNX, PCA, floor-fit, masa) dzieje się w PWA.

Dzięki temu PWA pozostaje jedną bazą kodu, a zmiana kamery wymaga tylko
zmiany kodu na płytce.

## Endpoint

```
ws://<board-ip>:8765/stream
```

Port 8765 przypisany umownie (8-7-6-5 = nietypowy, nie koliduje z typowymi
usługami). Można zmienić w konfiguracji serwera.

## Format ramki

Każda wiadomość WebSocket to **binarny payload** z układem:

```
[4 bajty LE: len(JSON)] [JSON] [RGB jako JPEG] [DEPTH jako PNG16]
```

Gdzie `JSON` ma strukturę:

```jsonc
{
  "w": 1280,               // szerokość obu strumieni (aligned)
  "h": 720,                // wysokość obu strumieni
  "rgbType": "jpeg",       // "jpeg" lub "png"
  "depthType": "png16",    // "png16" (grayscale 16-bit, 1 jednostka = 1 mm)
  "depthUnitM": 0.001,     // metry na jednostkę głębi (RealSense: 0.001)
  "fx": 920.5,             // intrinsics kamery głębi (po alignment)
  "fy": 920.5,
  "cx": 640.0,
  "cy": 360.0,
  "tsMs": 1732541234567    // timestamp w ms (monotonic albo epoch)
}
```

- `rgbOffset = 4 + len(JSON)`, `rgbLen = len(rgbPayload)`.
- `depthOffset = rgbOffset + rgbLen`, `depthLen = len(binary) - depthOffset`.

Serwer wie gdzie kończy się JPEG (footer `FFD9`), ale klient może też przyjąć
konwencję: **cała część po JSON i po RGB to depth**, więc wystarczy rozdzielić
RGB korzystając z końca markera JPEG.

Preferowany wariant (prostszy do parsowania po stronie PWA): wydzielić
nagłówek z polami `rgbLen` i `depthLen` tak:

```
[4 bajty LE: len(JSON)] [JSON] [RGB bytes] [DEPTH bytes]
```

i umieścić `rgbLen`, `depthLen` w samym JSON-ie — zamiast je wyliczać.

### JSON z długościami (wariant rekomendowany)

```jsonc
{
  "w": 1280, "h": 720,
  "rgbType": "jpeg", "depthType": "png16",
  "depthUnitM": 0.001,
  "fx": 920.5, "fy": 920.5, "cx": 640.0, "cy": 360.0,
  "tsMs": 1732541234567,
  "rgbLen": 48210,
  "depthLen": 312480
}
```

Parsowanie PWA:

```ts
const view = new DataView(arrayBuffer)
const jsonLen = view.getUint32(0, true)
const jsonStr = new TextDecoder().decode(
  new Uint8Array(arrayBuffer, 4, jsonLen),
)
const hdr = JSON.parse(jsonStr)
const rgbStart = 4 + jsonLen
const depthStart = rgbStart + hdr.rgbLen
const rgbBlob = new Blob(
  [new Uint8Array(arrayBuffer, rgbStart, hdr.rgbLen)],
  { type: 'image/jpeg' },
)
const depthBlob = new Blob(
  [new Uint8Array(arrayBuffer, depthStart, hdr.depthLen)],
  { type: 'image/png' },
)
```

## Parametry streamu

| Parametr | Rekomendacja | Uzasadnienie |
|----------|-------------:|--------------|
| Rozdzielczość | 1280×720 | Sweet-spot D435/D455 dla dokładności + FPS. |
| FPS | 15 | RealSense stabilnie wyrównuje głębię i kolor; wystarczy dla pomiaru. |
| Alignment | `rs.align(rs.stream.color)` | Głębia ma być w tym samym układzie pikselowym co RGB. |
| JPEG quality | 80 | Kompromis między przepustowością a jakością maski ONNX. |
| PNG16 compression | deflate level 1 | Szybkie po stronie płytki, PWA i tak dekompresuje szybko. |

Ruch przy 15 fps i 1280×720: ~30–50 KB JPEG + ~400 KB PNG16 = **~6–8 Mbps**.
To mieści się w Wi-Fi 2.4 GHz i spokojnie w 5 GHz.

## Reconnect / heartbeat

- Serwer wysyła ramki na bieżąco, bez pingów.
- PWA monitoruje `ws.readyState` i robi reconnect po 1s przy utracie.
- Opcjonalnie: pierwsza ramka po połączeniu może być JSON-only (bez RGB+depth),
  z polem `hello: true` oraz intrinsics / device id — do walidacji strojenia
  kamery przez użytkownika.

## Referencyjny serwer `bridge/realsense_server.py`

Poniżej szablon serwera w Pythonie, który działa na SBC (Linux, USB 3.0):

```python
"""
RealSense → WebSocket bridge.
Uruchom: python realsense_server.py --port 8765
"""

import asyncio
import io
import json
import struct
import time
import argparse

import numpy as np
import pyrealsense2 as rs
from PIL import Image
import websockets


def setup_pipeline(width=1280, height=720, fps=15):
    pipeline = rs.pipeline()
    config = rs.config()
    config.enable_stream(rs.stream.color, width, height, rs.format.bgr8, fps)
    config.enable_stream(rs.stream.depth, width, height, rs.format.z16, fps)
    profile = pipeline.start(config)
    align = rs.align(rs.stream.color)
    # Depth scale w metrach (D435 = 0.001)
    depth_sensor = profile.get_device().first_depth_sensor()
    depth_unit_m = depth_sensor.get_depth_scale()
    # Intrinsics po alignment (color stream)
    intr = profile.get_stream(rs.stream.color).as_video_stream_profile().get_intrinsics()
    return pipeline, align, depth_unit_m, intr


def encode_jpeg(bgr: np.ndarray, quality=80) -> bytes:
    img = Image.fromarray(bgr[..., ::-1])  # BGR → RGB
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality)
    return buf.getvalue()


def encode_png16(depth_mm: np.ndarray) -> bytes:
    img = Image.fromarray(depth_mm.astype(np.uint16), mode="I;16")
    buf = io.BytesIO()
    img.save(buf, format="PNG", compress_level=1)
    return buf.getvalue()


async def stream_client(ws, pipeline, align, depth_unit_m, intr):
    try:
        while True:
            frames = await asyncio.get_event_loop().run_in_executor(
                None, pipeline.wait_for_frames
            )
            aligned = align.process(frames)
            color_frame = aligned.get_color_frame()
            depth_frame = aligned.get_depth_frame()
            if not color_frame or not depth_frame:
                continue

            color = np.asanyarray(color_frame.get_data())
            # RealSense Z16 w jednostkach `depth_unit_m` metrów — konwertujemy do mm
            depth_raw = np.asanyarray(depth_frame.get_data()).astype(np.float32)
            depth_mm = np.clip(depth_raw * depth_unit_m * 1000.0, 0, 65535).astype(
                np.uint16
            )

            rgb_bytes = encode_jpeg(color)
            depth_bytes = encode_png16(depth_mm)

            header = {
                "w": intr.width,
                "h": intr.height,
                "rgbType": "jpeg",
                "depthType": "png16",
                "depthUnitM": 0.001,
                "fx": intr.fx,
                "fy": intr.fy,
                "cx": intr.ppx,
                "cy": intr.ppy,
                "tsMs": int(time.time() * 1000),
                "rgbLen": len(rgb_bytes),
                "depthLen": len(depth_bytes),
            }
            header_bytes = json.dumps(header).encode("utf-8")
            payload = (
                struct.pack("<I", len(header_bytes))
                + header_bytes
                + rgb_bytes
                + depth_bytes
            )
            await ws.send(payload)
    except websockets.ConnectionClosed:
        pass


async def main(port: int):
    pipeline, align, depth_unit_m, intr = setup_pipeline()
    print(f"RealSense OK. Listening on ws://0.0.0.0:{port}/stream")

    async def handler(ws):
        await stream_client(ws, pipeline, align, depth_unit_m, intr)

    async with websockets.serve(handler, "0.0.0.0", port, max_size=8_000_000):
        await asyncio.Future()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    asyncio.run(main(args.port))
```

Wymagania:

```
pip install pyrealsense2 websockets pillow numpy
```

## Po stronie PWA (niezaimplementowane w Fazie 1)

Szkic `DepthProvider`:

```ts
export interface DepthProvider {
  connect(): Promise<void>
  disconnect(): Promise<void>
  getLatestFrame(): { rgb: Blob; depth: DepthFrame; tsMs: number } | null
  onFrame(listener: (frame: { rgb: Blob; depth: DepthFrame; tsMs: number }) => void): void
}
```

Implementacje:

- `WebSocketDepthProvider(url)` — otwiera `ws://...`, parsuje binary payload jak
  powyżej, dekoduje JPEG (przez `createImageBitmap`) i PNG16 (przez
  `loadDepthPng16`), emituje eventy.
- `NullDepthProvider` — no-op; używany gdy user wyłączy źródło.

Synchronizacja timestampów: w pętli detekcji bierzemy najświeższy
`DepthFrame` z `getLatestFrame()` pod warunkiem `|tsMs(rgb) − tsMs(depth)| ≤ 200 ms`.
Dla źródła WS to zawsze spełnione (głębia i RGB idą razem w tej samej ramce).

## Milestones Fazy 2

1. Implementacja `WebSocketDepthProvider` w `web/src/lib/depthProvider.ts`.
2. Podłączenie do `CameraView` — jeżeli user ustawił URL WS, `computeFrameResult`
   dostaje aktualny `DepthFrame`.
3. UI w `SettingsPanel`: input URL WebSocket + status połączenia (idle /
   connecting / streaming @ X fps / error).
4. Test end-to-end: uruchomienie `realsense_server.py` na RPi 5 i PWA na
   telefonie w tej samej sieci Wi-Fi.
