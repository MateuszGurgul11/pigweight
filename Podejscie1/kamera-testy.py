import cv2
import depthai as dai
import numpy as np

# 1. Konfiguracja Pipeline
pipeline = dai.Pipeline()

cam_rgb = pipeline.create(dai.node.ColorCamera)
monoLeft = pipeline.create(dai.node.MonoCamera)
monoRight = pipeline.create(dai.node.MonoCamera)
stereo = pipeline.create(dai.node.StereoDepth)

xout_rgb = pipeline.create(dai.node.XLinkOut)
xout_depth = pipeline.create(dai.node.XLinkOut)

xout_rgb.setStreamName("rgb")
xout_depth.setStreamName("depth")

cam_rgb.setPreviewSize(640, 400)
cam_rgb.setInterleaved(False)
monoLeft.setResolution(dai.MonoCameraProperties.SensorResolution.THE_400_P)
monoRight.setResolution(dai.MonoCameraProperties.SensorResolution.THE_400_P)

# Ustawienia dla precyzyjnego dalmierza
stereo.setDefaultProfilePreset(dai.node.StereoDepth.PresetMode.HIGH_DENSITY)
stereo.setDepthAlign(dai.CameraBoardSocket.RGB)
stereo.setLeftRightCheck(True)
stereo.setSubpixel(True)

# Filtry wygładzające (żeby liczby nie skakały jak szalone)
conf = stereo.initialConfig.get()
conf.postProcessing.temporalFilter.enable = True # Stabilizacja klatek
conf.postProcessing.spatialFilter.enable = True  # Wypełnianie dziur
stereo.initialConfig.set(conf)

monoLeft.out.link(stereo.left)
monoRight.out.link(stereo.right)
cam_rgb.preview.link(xout_rgb.input)
stereo.depth.link(xout_depth.input)

print(">>> PISTOLET POMIAROWY: DYSTANS I PRZEŚWIT <<<")

with dai.Device(pipeline) as device:
    q_rgb = device.getOutputQueue(name="rgb", maxSize=4, blocking=False)
    q_depth = device.getOutputQueue(name="depth", maxSize=4, blocking=False)

    while True:
        frame_rgb = q_rgb.get().getCvFrame()
        frame_depth = q_depth.get().getFrame()

        h, w = frame_rgb.shape[:2]
        cx, cy = w // 2, h // 2 # Środek ekranu (celownik)

        # --- 1. ODLEGŁOŚĆ OD KAMERY (DYSTANS) ---
        # Średnia z małego obszaru, żeby pomiar był stabilny
        roi = frame_depth[cy-3:cy+4, cx-3:cx+4]
        dist_to_obj = np.mean(roi[roi > 0]) if np.any(roi > 0) else 0

        # --- 2. ODLEGŁOŚĆ OD ZIEMI (WYSOKOŚĆ) ---
        # Szukamy najniższego punktu w dolnej części ekranu (prawdopodobna podłoga)
        # Bierzemy pod uwagę tylko dolną połowę obrazu
        bottom_half = frame_depth[cy:, :]
        if np.any(bottom_half > 0):
            # Zakładamy, że najniższy punkt o niezerowej głębi to podłoże
            y_coords, x_coords = np.where(bottom_half > 0)
            ground_y_idx = y_coords.max()
            ground_x_idx = x_coords[y_coords.argmax()]
            
            # Punkt podłogi (skorygowany o przesunięcie cy)
            p_ground = (ground_x_idx, ground_y_idx + cy)
            dist_to_ground = frame_depth[p_ground[1], p_ground[0]]

            # Obliczamy różnicę wysokości (w przybliżeniu)
            # Jeśli trzymasz pistolet prosto, to różnica Y między środkiem a dołem
            # przemnożona przez dystans daje nam wysokość nad ziemią.
            pixel_diff = p_ground[1] - cy
            height_from_floor = (pixel_diff * dist_to_obj) / 440
        else:
            height_from_floor = 0
            p_ground = (cx, h-1)

        # --- WIZUALIZACJA ---
        # Celownik
        cv2.drawMarker(frame_rgb, (cx, cy), (0, 0, 255), cv2.MARKER_CROSS, 20, 2)
        # Linia do podłogi
        cv2.line(frame_rgb, (cx, cy), (cx, p_ground[1]), (255, 255, 0), 2)
        cv2.circle(frame_rgb, (cx, p_ground[1]), 5, (255, 0, 0), -1)

        # Wyświetlanie danych
        text_d = f"DYSTANS: {int(dist_to_obj)} mm"
        text_h = f"DO ZIEMI: {int(height_from_floor)} mm"

        # Tło dla tekstu
        cv2.rectangle(frame_rgb, (10, 10), (320, 90), (0, 0, 0), -1)
        cv2.putText(frame_rgb, text_d, (20, 40), cv2.FONT_HERSHEY_DUPLEX, 0.8, (255, 255, 255), 2)
        cv2.putText(frame_rgb, text_h, (20, 75), cv2.FONT_HERSHEY_DUPLEX, 0.8, (0, 255, 255), 2)

        cv2.imshow("PISTOLET DALMIERZ", frame_rgb)

        if cv2.waitKey(1) == ord('q'):
            break

cv2.destroyAllWindows()