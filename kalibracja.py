import depthai as dai
import numpy as np
import json
import time

# ── Budowa pipeline (DepthAI v3) ────────────────────────────────
pipeline = dai.Pipeline()

# Kamera RGB (nowe API v3: Camera zamiast ColorCamera)
cam_rgb = pipeline.create(dai.node.Camera)
cam_rgb.build(dai.CameraBoardSocket.CAM_A)

# Wyjście RGB 1920x1080 jako BGR
rgb_out  = cam_rgb.requestOutput((1920, 1080), type=dai.ImgFrame.Type.BGR888p)
rgb_queue = rgb_out.createOutputQueue(maxSize=2, blocking=False)

# StereoDepth — autoCreateCameras=True automatycznie tworzy węzły
# mono (CAM_B / CAM_C), eliminując błąd "could not map AUTO camera socket"
stereo = pipeline.create(dai.node.StereoDepth)
stereo.build(
    autoCreateCameras=True,
    presetMode=dai.node.StereoDepth.PresetMode.ACCURACY
)
# Wyrównaj mapę głębi do układu kamery RGB
stereo.setDepthAlign(dai.CameraBoardSocket.CAM_A)
stereo.setOutputSize(1920, 1080)

depth_queue = stereo.depth.createOutputQueue(maxSize=2, blocking=False)

# ── Funkcja kalibracji ──────────────────────────────────────────
def calibrate(pipeline):
    """
    Pobiera rzeczywiste fx z kalibracji kamery OAK-D S2,
    mierzy głębię w środku kadru i wyznacza scale_factor [cm/px].
    """
    # Odczyt rzeczywistej ogniskowej z danych kalibracyjnych kamery
    device    = pipeline.getDefaultDevice()
    calib     = device.readCalibration()
    # getCameraIntrinsics zwraca macierz 3x3; M[0][0] to fx
    intrinsics = calib.getCameraIntrinsics(
        dai.CameraBoardSocket.CAM_A,
        1920, 1080
    )
    fx = intrinsics[0][0]
    print(f"   Rzeczywiste fx kamery RGB : {fx:.1f} px")

    # Poczekaj na pierwszą stabilną klatkę głębi
    print("   Czekam na stabilny obraz głębi...")
    for _ in range(10):          # odrzuć pierwsze 10 klatek (warmup)
        depth_queue.get()
        rgb_queue.get()
    time.sleep(0.3)

    depth_frame = depth_queue.get().getFrame()   # wartości w mm (uint16)
    _           = rgb_queue.get()                # synchronizacja (nieużywane)

    # Środkowy ROI 40x40 px → solidna mediana
    cy, cx = depth_frame.shape[0] // 2, depth_frame.shape[1] // 2
    roi = depth_frame[cy-20:cy+20, cx-20:cx+20]

    valid = roi[roi > 0]
    if len(valid) == 0:
        raise RuntimeError(
            "Brak odczytu głębi w centrum kadru.\n"
            "Upewnij się, że kamera wskazuje na równą powierzchnię (podłogę)\n"
            "z odległości 1–3 m i jest wystarczające oświetlenie."
        )

    Z_mm = float(np.median(valid))
    Z_cm = Z_mm / 10.0

    # Przelicznik: ile cm ma 1 piksel na wysokości Z_cm
    scale_cm_per_px = Z_cm / fx

    result = {
        "height_cm":        round(Z_cm, 1),
        "fx_px":            round(fx, 2),
        "scale_cm_per_px":  round(scale_cm_per_px, 6),
        "px_per_cm":        round(1.0 / scale_cm_per_px, 2),
        "fov_width_cm":     round(1920 * scale_cm_per_px, 1),
        "fov_height_cm":    round(1080 * scale_cm_per_px, 1),
        "timestamp":        time.strftime("%Y-%m-%dT%H:%M:%S"),
    }

    with open("calibration.json", "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    print()
    print("╔══════════════════════════════════════════╗")
    print("║        ✅  KALIBRACJA ZAKOŃCZONA          ║")
    print("╠══════════════════════════════════════════╣")
    print(f"║  Wysokość kamery   : {Z_cm:>8.1f} cm         ║")
    print(f"║  Ogniskowa fx      : {fx:>8.1f} px         ║")
    print(f"║  Skala             : {result['px_per_cm']:>8.2f} px/cm      ║")
    print(f"║  1 piksel = {scale_cm_per_px*10:>6.3f} mm                  ║")
    print(f"║  Widok (szer×wys)  : {result['fov_width_cm']:.0f} × {result['fov_height_cm']:.0f} cm   ║")
    print("╠══════════════════════════════════════════╣")
    print("║  Zapisano: calibration.json              ║")
    print("╚══════════════════════════════════════════╝")

    return result

# ── Główna pętla ────────────────────────────────────────────────
print("=" * 44)
print("  KALIBRACJA KAMERY OAK-D S2  (v3 API)")
print("=" * 44)
print()
print("Instrukcja:")
print("  1. Skieruj kamerę pionowo w dół (90°)")
print("  2. Upewnij się, że poziomica wskazuje poziom")
print("  3. Naciśnij ENTER, gdy jesteś gotowy")
print()

pipeline.start()
with pipeline:
    input(">>> Naciśnij ENTER aby wykonać kalibrację... ")
    print()
    cal = calibrate(pipeline)
