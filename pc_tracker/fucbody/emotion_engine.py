import time
import math
from dataclasses import dataclass, field
from collections import deque
from typing import Dict, List, Tuple, Optional

@dataclass
class Personality:
    """
    Kişilik modülasyonu için Big Five benzeri parametreler (0.0 - 1.0 aralığı).
    """
    extraversion: float = 0.5  # Dışa dönüklük: Pozitif olaylara tepkiyi artırır.
    neuroticism: float = 0.5   # Nörotizm: Negatif olaylara tepkiyi artırır.
    openness: float = 0.5      # Açıklık: Habituation (alışma) hızını etkiler.

@dataclass
class EmotionState:
    """PAD modeli: Her bir boyut -1.0 ile 1.0 arasında değer alır."""
    pleasure: float = 0.0
    arousal: float = 0.0
    dominance: float = 0.0

@dataclass
class EmotionEvent:
    """Bir olayın temel etkisini tutar."""
    name: str
    pleasure_delta: float
    arousal_delta: float
    dominance_delta: float

class EmotionEngine:
    def __init__(self, personality: Optional[Personality] = None, decay_rates: Optional[Dict[str, float]] = None):
        """
        EmotionEngine Başlatıcısı
        :param personality: Robotun karakterini belirleyen parametreler.
        :param decay_rates: Boyutların her saniyedeki sönümleme katsayıları (örn: arousal hızlı söner).
        """
        self.personality = personality or Personality()
        self.state = EmotionState()
        
        # Saniyede sıfıra yaklaşma oranı (Örn: arousal saniyede %10 düşer)
        self.decay_rates = decay_rates or {
            "pleasure": 0.05,
            "arousal": 0.15,
            "dominance": 0.02
        }
        
        self.registered_events: Dict[str, EmotionEvent] = {}
        
        # Habituation (Alışma) için geçmiş olaylar: (olay_adi, timestamp)
        self.event_memory = deque(maxlen=20)
        
        # Mood (Duygudurum) için son N dakikanın hareketli ortalaması
        self.mood_history = deque(maxlen=60) # Ortalama 60 ölçüm (örn. 60 saniye)
        self.current_mood = EmotionState()
        self.last_mood_update = time.time()
        
        # Debug ve Loglama için dairesel tampon (Ring buffer)
        self.logger = deque(maxlen=100)
        
        self._log("EmotionEngine başlatıldı.")

    def _log(self, message: str):
        """Dahili loglama."""
        log_entry = f"[{time.strftime('%H:%M:%S')}] {message}"
        self.logger.append(log_entry)

    def register_event(self, name: str, p_delta: float, a_delta: float, d_delta: float):
        """Sisteme dışarıdan yeni bir olay kaydeder."""
        self.registered_events[name] = EmotionEvent(name, p_delta, a_delta, d_delta)
        self._log(f"Olay eklendi: {name} (P:{p_delta}, A:{a_delta}, D:{d_delta})")

    def _calculate_habituation_multiplier(self, event_name: str) -> float:
        """
        Aynı olay kısa sürede çok sık tetiklenirse etkisini düşürür.
        Kişiliğin "openness" (açıklık) değeri yüksekse robot çok daha çabuk sıkılır (alışır).
        """
        current_time = time.time()
        occurrences = 0
        
        for name, timestamp in self.event_memory:
            if name == event_name:
                # Son 10 saniye içindeki aynı olaylara bak
                if current_time - timestamp < 10.0:
                    occurrences += 1

        # Her tekrar etkiyi azaltır. Openness yüksekse etki daha da hızlı düşer.
        boredom_factor = 0.1 + (self.personality.openness * 0.2) 
        multiplier = max(0.1, 1.0 - (occurrences * boredom_factor))
        return multiplier

    def trigger_event(self, event_names: List[str]):
        """
        Bir veya birden fazla olayı aynı anda tetikler. Çoklu olaylar toplanır.
        """
        total_p_delta, total_a_delta, total_d_delta = 0.0, 0.0, 0.0
        
        for name in event_names:
            if name not in self.registered_events:
                self._log(f"Uyarı: Bilinmeyen olay -> {name}")
                continue
                
            event = self.registered_events[name]
            
            # 1. Habituation: Etkiyi zayıflat
            habituation_mult = self._calculate_habituation_multiplier(name)
            
            # 2. Kişilik Modülasyonu: 
            # Pozitif (pleasure > 0) olaylarda Dışadönüklük (Extraversion) etkiyi artırır
            # Negatif olaylarda Nörotizm (Neuroticism) etkiyi artırır
            p_mult = 1.0
            if event.pleasure_delta > 0:
                p_mult += (self.personality.extraversion - 0.5)
            elif event.pleasure_delta < 0:
                p_mult += (self.personality.neuroticism - 0.5)

            final_p = event.pleasure_delta * habituation_mult * p_mult
            final_a = event.arousal_delta * habituation_mult # Arousal genelde sönümlemeden etkilenir
            final_d = event.dominance_delta * habituation_mult

            total_p_delta += final_p
            total_a_delta += final_a
            total_d_delta += final_d
            
            # Hafızaya ekle
            self.event_memory.append((name, time.time()))
        
        # 3. Mevcut duruma uygula ve -1.0 ile 1.0 arasına sıkıştır (clipping)
        self.state.pleasure = max(-1.0, min(1.0, self.state.pleasure + total_p_delta))
        self.state.arousal = max(-1.0, min(1.0, self.state.arousal + total_a_delta))
        self.state.dominance = max(-1.0, min(1.0, self.state.dominance + total_d_delta))
        
        if event_names:
            self._log(f"Tetiklendi: {event_names} | Yeni State: P={self.state.pleasure:.2f}, A={self.state.arousal:.2f}")

    def update(self, dt: float):
        """
        Homeostaz: Duyguları zamanla sıfıra (nötr duruma) doğru çeker.
        Her FPS döngüsünde (dt = delta time saniye cinsinden) çağrılır.
        """
        # Üssel sönümleme: state = state * (1 - decay_rate)^dt
        # Ancak dt küçükse, basit euler: state -= state * decay_rate * dt
        self.state.pleasure -= self.state.pleasure * self.decay_rates["pleasure"] * dt
        self.state.arousal -= self.state.arousal * self.decay_rates["arousal"] * dt
        self.state.dominance -= self.state.dominance * self.decay_rates["dominance"] * dt

        # Mood güncellemesi (Her 1 saniyede bir örneklem al)
        current_time = time.time()
        if current_time - self.last_mood_update >= 1.0:
            self.mood_history.append((self.state.pleasure, self.state.arousal, self.state.dominance))
            self._update_mood()
            self.last_mood_update = current_time

    def _update_mood(self):
        """Uzun vadeli duygudurumu (Mood) hesaplar."""
        if not self.mood_history:
            return
            
        avg_p = sum(item[0] for item in self.mood_history) / len(self.mood_history)
        avg_a = sum(item[1] for item in self.mood_history) / len(self.mood_history)
        avg_d = sum(item[2] for item in self.mood_history) / len(self.mood_history)
        
        self.current_mood.pleasure = avg_p
        self.current_mood.arousal = avg_a
        self.current_mood.dominance = avg_d

    def get_esp32_state(self) -> Tuple[str, float, str]:
        """
        ESP32'nin veya sistemin anlayabileceği formatta dominant duyguyu çıkarır.
        PAD haritalaması ile en baskın state'i belirler.
        Return: (state_name, intensity, description)
        """
        p, a, d = self.state.pleasure, self.state.arousal, self.state.dominance
        
        # Basit Öklid uzaklık hesabı için örnek duygu koordinatları (P, A)
        emotions = {
            "HAPPY": (0.8, 0.4),
            "SAD": (-0.8, -0.4),
            "ANGRY": (-0.5, 0.8),
            "RELAXED": (0.5, -0.6),
            "SURPRISED": (0.2, 0.9),
            "SLEEPY": (0.0, -0.8),
            "NEUTRAL": (0.0, 0.0)
        }

        best_emotion = "NEUTRAL"
        min_distance = float('inf')
        
        for name, (target_p, target_a) in emotions.items():
            # Dominance bu örnekte mesafeye katılmıyor ama eklenebilir.
            dist = math.sqrt((p - target_p)**2 + (a - target_a)**2)
            if dist < min_distance:
                min_distance = dist
                best_emotion = name

        # Yoğunluk (Intensity) = Orijine (0,0) olan uzaklık. Maks: ~1.414 -> 1.0 ile sınırla
        intensity = min(1.0, math.sqrt(p**2 + a**2))
        
        # Threshold: Yoğunluk çok düşükse NEUTRAL ver
        if intensity < 0.15:
            best_emotion = "NEUTRAL"
            intensity = 0.0
            
        description = f"Mood: P={self.current_mood.pleasure:.2f}, A={self.current_mood.arousal:.2f}"
        return best_emotion, intensity, description

    def get_debug_info(self) -> Dict:
        """Tüm iç değerleri sözlük olarak döner."""
        return {
            "pleasure": round(self.state.pleasure, 3),
            "arousal": round(self.state.arousal, 3),
            "dominance": round(self.state.dominance, 3),
            "mood_pleasure": round(self.current_mood.pleasure, 3),
            "mood_arousal": round(self.current_mood.arousal, 3),
            "recent_logs": list(self.logger)[-5:] # Son 5 log
        }

if __name__ == "__main__":
    # Örnek Kullanım ve Simülasyon
    print("--- EmotionEngine Simülasyonu Başlatılıyor ---")
    
    # Nörotik bir kişilik yaratalım (Negatif olaylardan çok etkilenen, pozitiflere az tepki veren)
    bot_personality = Personality(extraversion=0.2, neuroticism=0.9, openness=0.5)
    engine = EmotionEngine(personality=bot_personality)

    # Olayları Tanımlayalım
    engine.register_event("user_smiled", p_delta=0.4, a_delta=0.2, d_delta=0.1)
    engine.register_event("loud_noise", p_delta=-0.3, a_delta=0.8, d_delta=-0.2)
    engine.register_event("scold", p_delta=-0.6, a_delta=0.5, d_delta=-0.5)

    print("\n[Zaman: 0.0s] Başlangıç State:", engine.get_esp32_state())

    print("\n[Zaman: 1.0s] Kullanıcı gülümsedi!")
    engine.trigger_event(["user_smiled"])
    print("State:", engine.get_esp32_state())

    print("\n[Zaman: 2.0s] Yüksek ses geldi ve Azarlandı!")
    # Aynı anda iki olay
    engine.trigger_event(["loud_noise", "scold"])
    print("State:", engine.get_esp32_state())
    print("Debug Info:", engine.get_debug_info())

    print("\n[Zaman: 3.0s] Kullanıcı art arda çok sık gülümsüyor (Habituation Testi)...")
    for _ in range(5):
        engine.trigger_event(["user_smiled"])
    print("State:", engine.get_esp32_state())
    print("Açıklama: Etki giderek azalır çünkü robota aynı olay 5 kez tekrarlandı (Sıkıldı).")

    print("\n[Zaman: 4.0s - 14.0s] Zaman Geçiyor (Decay / Homeostasis Testi)...")
    # Her saniye update(dt=1.0) çağıralım
    for s in range(10):
        engine.update(dt=1.0)
        time.sleep(0.1) # Gerçek bekleme yapmayıp hızlı simüle ediyoruz
        
    print("10 Saniye Sonra State:", engine.get_esp32_state())
    print("Debug Info:", engine.get_debug_info())
    print("\nAçıklama: Duygular yavaşça sönümlendi ve nötre yaklaştı.")
