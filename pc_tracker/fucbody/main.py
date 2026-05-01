import cv2
import mediapipe as mp
from mediapipe.tasks import python
from mediapipe.tasks.python import vision
import asyncio
import threading
import queue
import time
import os
import urllib.request
from bleak import BleakClient, BleakScanner

from emotion_engine import EmotionEngine, Personality

# --- Ayarlar ---
SERVICE_UUID = "4fafc201-1fb5-459e-8fcc-c5c9c331914b"
CHAR_UUID = "beb5483e-36e1-4688-b7f5-ea07361b26a8"
DEVICE_NAME = "FocusBuddy"

state_queue = queue.Queue()

# --- BLE Asenkron İşlemleri ---
async def ble_worker(q):
    print("BLE: Tarama başlatılıyor...")
    devices = await BleakScanner.discover()
    target_device = None
    for d in devices:
        if d.name == DEVICE_NAME:
            target_device = d
            break
    
    if not target_device:
        print(f"BLE: '{DEVICE_NAME}' bulunamadı. Lütfen ESP32'nin açık olduğundan emin olun.")
        return

    print(f"BLE: Cihaz bulundu: {target_device.address}. Bağlanılıyor...")
    try:
        async with BleakClient(target_device.address) as client:
            print("BLE: Bağlantı başarılı!")
            current_state = None
            
            while True:
                try:
                    new_state = q.get_nowait()
                except queue.Empty:
                    await asyncio.sleep(0.1)
                    continue
                
                if new_state != current_state:
                    print(f"BLE: Durum gönderiliyor -> {new_state}")
                    await client.write_gatt_char(CHAR_UUID, new_state.encode('utf-8'))
                    current_state = new_state
                
                await asyncio.sleep(0.05)
    except Exception as e:
        print(f"BLE: Bağlantı hatası: {e}")

def run_ble_loop(q):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(ble_worker(q))

def download_model_if_needed():
    model_path = 'face_landmarker.task'
    if not os.path.exists(model_path):
        print("MediaPipe modeli indiriliyor (yaklaşık 9 MB)... Lütfen bekleyin.")
        url = "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task"
        urllib.request.urlretrieve(url, model_path)
        print("Model başarıyla indirildi.")
    return model_path

# --- Görüntü İşleme ve Yüz Takibi ---
def main():
    ble_thread = threading.Thread(target=run_ble_loop, args=(state_queue,), daemon=True)
    ble_thread.start()

    model_path = download_model_if_needed()

    # Face Landmarker Ayarları
    base_options = python.BaseOptions(model_asset_path=model_path)
    options = vision.FaceLandmarkerOptions(
        base_options=base_options,
        output_face_blendshapes=True,
        num_faces=1
    )
    detector = vision.FaceLandmarker.create_from_options(options)

    # Emotion Engine Başlatma
    robot_personality = Personality(extraversion=0.7, neuroticism=0.4, openness=0.8)
    engine = EmotionEngine(personality=robot_personality)

    cap = cv2.VideoCapture(0)
    time.sleep(1)
    
    last_face_time = time.time()
    away_timeout = 2.0
    
    print("Kamera: Başlatıldı. Arka planda çalışıyor. Çıkmak için terminalde 'Ctrl + C' tuşlarına basın.")
    
    last_sent_state = "EMO:SLEEPY|LOOK:CENTER"
    state_queue.put(last_sent_state)

    last_loop_time = time.time()

    # Bakış yönü (LOOK) filtresi için
    look_command = "LOOK:CENTER"
    pending_look_command = "LOOK:CENTER"
    look_change_time = time.time()

    try:
        while cap.isOpened():
            success, image = cap.read()
            if not success:
                continue

            current_time = time.time()
            dt = current_time - last_loop_time
            last_loop_time = current_time
            
            # Motoru güncelle (İnterpolasyon ile yavaşça hedefe kay)
            engine.update(dt)

            image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=image_rgb)
            
            detection_result = detector.detect(mp_image)

            if len(detection_result.face_landmarks) > 0:
                last_face_time = current_time
                
                # Blendshapes (İfade skorları)
                blendshapes = detection_result.face_blendshapes[0]
                scores = {category.category_name: category.score for category in blendshapes}
                
                jaw_open = scores.get('jawOpen', 0)
                smile_l = scores.get('mouthSmileLeft', 0)
                smile_r = scores.get('mouthSmileRight', 0)
                frown_l = scores.get('mouthFrownLeft', 0)
                frown_r = scores.get('mouthFrownRight', 0)
                brow_down_l = scores.get('browDownLeft', 0)
                brow_down_r = scores.get('browDownRight', 0)
                
                smile_score = (smile_l + smile_r) / 2.0
                frown_score = max((frown_l + frown_r) / 2.0, (brow_down_l + brow_down_r) / 2.0)

                # Hedef PAD hesaplama (Doğal yüzü yoksaymak için safe margin kullanıyoruz)
                # frown_score 0.35'in altındaysa 0 kabul edilir.
                safe_smile = max(0.0, smile_score - 0.1) * 1.5
                safe_frown = max(0.0, frown_score - 0.35) * 2.0 
                
                target_p = min(1.0, safe_smile) - min(1.0, safe_frown)
                target_a = min(1.0, jaw_open * 2.0)
                
                # Hedefi motora ver (Motor dt ile yavaşça bu noktaya akacak)
                engine.set_target_state(target_p, target_a, 0.0)

                # Landmarks (Pozisyon skorları)
                landmarks = detection_result.face_landmarks[0]
                nose_x, nose_y = landmarks[1].x, landmarks[1].y
                top_y = landmarks[10].y
                chin_y = landmarks[152].y
                left_x = landmarks[234].x
                right_x = landmarks[454].x
                
                face_height = chin_y - top_y
                face_width = right_x - left_x
                
                if face_height > 0 and face_width > 0:
                    v_ratio = (nose_y - top_y) / face_height
                    h_ratio = (nose_x - left_x) / face_width
                    
                    new_look = "LOOK:CENTER"
                    if v_ratio < 0.45:
                        new_look = "LOOK:UP"
                    elif v_ratio > 0.65:
                        new_look = "LOOK:DOWN"
                    elif h_ratio > 0.65:
                        new_look = "LOOK:LEFT"
                    elif h_ratio < 0.35:
                        new_look = "LOOK:RIGHT"
                    
                    # Titremeyi önlemek için yön değişiminde 0.3s bekleme (Low-pass zaman filtresi)
                    if new_look != pending_look_command:
                        pending_look_command = new_look
                        look_change_time = current_time
                    elif current_time - look_change_time > 0.3:
                        look_command = pending_look_command
                        
                    cv2.putText(image, f"T_P:{target_p:.2f} T_A:{target_a:.2f}", (20, 70), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 1)
                    cv2.putText(image, f"S:{smile_score:.2f} F:{frown_score:.2f}", (20, 100), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 1)
            else:
                if current_time - last_face_time > away_timeout:
                    # Uzaktayken üzgün ve uykulu hedefine yavaşça geç
                    engine.set_target_state(-0.2, -0.8, -0.5)
                    look_command = "LOOK:CENTER"
            
            emotion_name, intensity, desc = engine.get_esp32_state()
            new_state = f"EMO:{emotion_name}|{look_command}"
            
            if new_state != last_sent_state:
                state_queue.put(new_state)
                last_sent_state = new_state

            cv2.putText(image, f"State: {new_state}", (20, 140), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)

            time.sleep(0.01)

    except KeyboardInterrupt:
        print("\nKullanıcı tarafından durduruldu.")
    finally:
        cap.release()
        cv2.destroyAllWindows()
        print("Program sonlandırıldı.")

if __name__ == "__main__":
    main()
