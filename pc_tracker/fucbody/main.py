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
    # Biraz açık ve dışadönük bir robot
    robot_personality = Personality(extraversion=0.7, neuroticism=0.4, openness=0.8)
    engine = EmotionEngine(personality=robot_personality)
    
    # Olayları Kaydet
    engine.register_event("smile", p_delta=0.4, a_delta=0.2, d_delta=0.1)
    engine.register_event("frown", p_delta=-0.4, a_delta=0.2, d_delta=-0.2)
    engine.register_event("talking", p_delta=0.1, a_delta=0.5, d_delta=0.3)
    engine.register_event("away", p_delta=-0.1, a_delta=-0.4, d_delta=-0.3)

    cap = cv2.VideoCapture(0)
    time.sleep(1)
    
    last_face_time = time.time()
    away_timeout = 2.0
    
    print("Kamera: Başlatıldı. Arka planda çalışıyor. Çıkmak için terminalde 'Ctrl + C' tuşlarına basın.")
    
    last_sent_state = "EMO:SLEEPY|LOOK:CENTER"
    state_queue.put(last_sent_state)

    last_loop_time = time.time()

    try:
        while cap.isOpened():
            success, image = cap.read()
            if not success:
                continue

            current_time = time.time()
            dt = current_time - last_loop_time
            last_loop_time = current_time
            
            # Motoru güncelle (Decay)
            engine.update(dt)

            image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=image_rgb)
            
            detection_result = detector.detect(mp_image)

            triggered_events = []
            look_command = "LOOK:CENTER"

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
                    
                    # Olay Tetikleme (Thresholds)
                    # Sadece net ifadelerde tetikle, yoksa gereksiz spam yapar
                    if jaw_open > 0.15:
                        triggered_events.append("talking")
                    if smile_score > 0.4:
                        triggered_events.append("smile")
                    if frown_score > 0.4:
                        triggered_events.append("frown")
                    
                    # Baş Açısı -> Sadece Look Command
                    if v_ratio < 0.45:
                        look_command = "LOOK:UP"
                    elif v_ratio > 0.65:
                        look_command = "LOOK:DOWN"
                    elif h_ratio > 0.65:
                        look_command = "LOOK:LEFT"
                    elif h_ratio < 0.35:
                        look_command = "LOOK:RIGHT"
                        
                    cv2.putText(image, f"Smile:{smile_score:.2f} Frown:{frown_score:.2f}", (20, 70), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 1)
                    cv2.putText(image, f"Jaw:{jaw_open:.2f} V:{v_ratio:.2f} H:{h_ratio:.2f}", (20, 100), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 1)
            else:
                if current_time - last_face_time > away_timeout:
                    triggered_events.append("away")
                    
            # Olayları motora gönder
            if triggered_events:
                engine.trigger_event(triggered_events)
            
            # Yeni ESP32 formatı
            emotion_name, intensity, desc = engine.get_esp32_state()
            new_state = f"EMO:{emotion_name}|{look_command}"
            
            if new_state != last_sent_state:
                state_queue.put(new_state)
                last_sent_state = new_state

            cv2.putText(image, f"State: {new_state}", (20, 140), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)

            # Döngünün çok hızlı çalışıp CPU'yu yormaması için küçük bir bekleme
            time.sleep(0.01)

    except KeyboardInterrupt:
        print("\nKullanıcı tarafından durduruldu.")
    finally:
        cap.release()
        cv2.destroyAllWindows()
        print("Program sonlandırıldı.")

if __name__ == "__main__":
    main()
