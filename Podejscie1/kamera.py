import depthai as dai
import cv2
import numpy as np
import os
from datetime import datetime

def record_pig_session(pig_id: str, weight_kg: float, output_dir: str = "dataset"):
    """
    Nagrywa RGB + depth dla jednej świni.
    Naciśnij SPACJA aby zacząć/zatrzymać nagranie.
    Naciśnij Q aby zakończyć i przejść do następnej świni.
    """
    
    # Utwórz folder
    session_dir = os.path.join(output_dir, f"pig_{pig_id:03d}")
    os.makedirs(session_dir, exist_ok=True)
    
    # Zapisz wagę
    with open(os.path.join(session_dir, "weight_kg.txt"), "w") as f:
        f.write(str(weight_kg))
    
    # Bufory na klatki — zapełniane wewnątrz pipeline'u
    rgb_frames: list = []
    depth_frames: list = []
    recording = False

    print(f"\n🐷 Świnia #{pig_id} | Waga: {weight_kg} kg")
    print("SPACJA = start/stop nagrania | Q = zapisz i wyjdź\n")

    # Konfiguracja OAK-D S2 (depthai v3: pipeline jako kontekstowy menedżer)
    with dai.Pipeline() as pipeline:
        # RGB kamera
        cam_rgb = pipeline.create(dai.node.ColorCamera)
        cam_rgb.setResolution(dai.ColorCameraProperties.SensorResolution.THE_1080_P)
        cam_rgb.setFps(15)  # 15fps wystarczy, mniejszy plik

        # Kamera głębi
        mono_left = pipeline.create(dai.node.MonoCamera)
        mono_right = pipeline.create(dai.node.MonoCamera)
        stereo = pipeline.create(dai.node.StereoDepth)

        mono_left.setResolution(dai.MonoCameraProperties.SensorResolution.THE_400_P)
        mono_right.setResolution(dai.MonoCameraProperties.SensorResolution.THE_400_P)
        mono_left.setBoardSocket(dai.CameraBoardSocket.CAM_B)
        mono_right.setBoardSocket(dai.CameraBoardSocket.CAM_C)

        # depthai v3: HIGH_DENSITY usunięte → FAST_DENSITY (gęsta mapa głębi)
        stereo.setDefaultProfilePreset(dai.node.StereoDepth.PresetMode.FAST_DENSITY)
        stereo.setDepthAlign(dai.CameraBoardSocket.CAM_A)  # depth wyrównany do RGB (CAM_A)

        mono_left.out.link(stereo.left)
        mono_right.out.link(stereo.right)

        # depthai v3: brak XLinkOut — kolejki tworzymy bezpośrednio na outputach
        q_rgb = cam_rgb.video.createOutputQueue(maxSize=4, blocking=False)
        q_depth = stereo.depth.createOutputQueue(maxSize=4, blocking=False)

        pipeline.start()

        while pipeline.isRunning():
            in_rgb = q_rgb.get()
            in_depth = q_depth.get()

            frame_rgb = in_rgb.getCvFrame()
            frame_depth = in_depth.getFrame()

            # Wizualizacja głębi (dla podglądu)
            depth_vis = cv2.normalize(frame_depth, None, 0, 255, cv2.NORM_MINMAX)
            depth_vis = cv2.applyColorMap(depth_vis.astype(np.uint8), cv2.COLORMAP_JET)

            # Nakładka informacyjna
            status = "⏺ NAGRYWA" if recording else "⏸ PAUZA"
            cv2.putText(frame_rgb, f"{status} | Swinia #{pig_id} | {weight_kg}kg",
                       (10, 40), cv2.FONT_HERSHEY_SIMPLEX, 1,
                       (0, 0, 255) if recording else (0, 255, 0), 2)
            cv2.putText(frame_rgb, f"Klatek RGB: {len(rgb_frames)}",
                       (10, 80), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

            # Podgląd (RGB po lewej, depth po prawej)
            depth_vis_resized = cv2.resize(depth_vis, (frame_rgb.shape[1]//2, frame_rgb.shape[0]//2))
            rgb_small = cv2.resize(frame_rgb, (frame_rgb.shape[1]//2, frame_rgb.shape[0]//2))
            preview = np.hstack([rgb_small, depth_vis_resized])
            cv2.imshow("OAK-D S2 | Nagrywanie", preview)

            if recording:
                rgb_frames.append(frame_rgb)
                depth_frames.append(frame_depth)

            key = cv2.waitKey(1) & 0xFF
            if key == ord(' '):  # SPACJA
                recording = not recording
                if recording:
                    print("▶ Start nagrania...")
                else:
                    print(f"⏸ Pauza. Nagrano {len(rgb_frames)} klatek")
            elif key == ord('q'):
                break

    cv2.destroyAllWindows()
    
    # Zapisz nagrania
    if rgb_frames:
        # RGB video
        rgb_path = os.path.join(session_dir, "rgb_video.mp4")
        h, w = rgb_frames[0].shape[:2]
        writer = cv2.VideoWriter(rgb_path, cv2.VideoWriter_fourcc(*'mp4v'), 15, (w, h))
        for f in rgb_frames:
            writer.write(f)
        writer.release()
        
        # Depth jako numpy (zachowuje rzeczywiste wartości mm)
        depth_path = os.path.join(session_dir, "depth_frames.npy")
        np.save(depth_path, np.array(depth_frames))
        
        print(f"✅ Zapisano: {len(rgb_frames)} klatek RGB + depth")
        print(f"   📁 {session_dir}")
    else:
        print("⚠️ Brak nagranych klatek!")


# === GŁÓWNA PĘTLA SESJI ===
if __name__ == "__main__":
    CAMERA_HEIGHT_CM = float(input("Podaj wysokość kamery od podłogi [cm]: "))
    
    # Zapisz wysokość kamery
    os.makedirs("dataset/calibration", exist_ok=True)
    with open("dataset/calibration/camera_height_cm.txt", "w") as f:
        f.write(str(CAMERA_HEIGHT_CM))
    
    pig_id = 1
    while True:
        weight = input(f"\nPodaj wagę świni #{pig_id} [kg] (lub 'q' aby zakończyć): ")
        if weight.lower() == 'q':
            break
        try:
            record_pig_session(pig_id, float(weight))
            pig_id += 1
        except ValueError:
            print("❌ Podaj liczbę np. 94.5")
    7
    print(f"\n🏁 Sesja zakończona. Nagrano {pig_id-1} świń.")
    print("Dataset gotowy do trenowania modelu!")