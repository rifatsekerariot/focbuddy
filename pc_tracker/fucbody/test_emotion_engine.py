import unittest
import time
from emotion_engine import EmotionEngine, Personality

class TestEmotionEngine(unittest.TestCase):
    
    def setUp(self):
        # Her testten önce taze bir engine oluşturulur.
        # Açıklık yüksek, böylece habituation testleri daha kolay gözlemlenir.
        self.engine = EmotionEngine(personality=Personality(openness=1.0))
        self.engine.register_event("positive_event", p_delta=0.5, a_delta=0.2, d_delta=0.0)
        self.engine.register_event("negative_event", p_delta=-0.5, a_delta=0.5, d_delta=-0.2)

    def test_initial_state(self):
        self.assertEqual(self.engine.state.pleasure, 0.0)
        self.assertEqual(self.engine.state.arousal, 0.0)
        self.assertEqual(self.engine.state.dominance, 0.0)

    def test_trigger_single_event(self):
        self.engine.trigger_event(["positive_event"])
        self.assertGreater(self.engine.state.pleasure, 0.0)
        self.assertGreater(self.engine.state.arousal, 0.0)

    def test_habituation(self):
        # İlk tetikleme
        self.engine.trigger_event(["positive_event"])
        pleasure_after_first = self.engine.state.pleasure
        
        # Sistemi nötre yakın çekelim veya direkt ikinci kez aynı olayı tetikleyelim.
        # İkinci tetiklemenin etkisi (delta), habituation yüzünden ilk tetiklemeden daha az olmalıdır.
        self.engine.trigger_event(["positive_event"])
        pleasure_after_second = self.engine.state.pleasure
        
        delta1 = pleasure_after_first - 0.0
        delta2 = pleasure_after_second - pleasure_after_first
        
        self.assertLess(delta2, delta1, "Aynı olayın ardışık tetiklenmesinde etki (delta) azalmalıdır (Habituation başarısız).")

    def test_decay_over_time(self):
        self.engine.trigger_event(["positive_event"])
        initial_pleasure = self.engine.state.pleasure
        
        # 1 saniyelik zaman geçişi simülasyonu
        self.engine.update(dt=1.0)
        
        pleasure_after_decay = self.engine.state.pleasure
        self.assertLess(pleasure_after_decay, initial_pleasure, "Decay (Sönümleme) çalışmadı.")
        self.assertGreater(pleasure_after_decay, 0.0, "Sönümleme değeri sıfırın altına düşürdü.")

    def test_personality_modulation(self):
        # Dışadönük (Extravert) vs İçedönük (Introvert)
        engine_extravert = EmotionEngine(personality=Personality(extraversion=1.0))
        engine_introvert = EmotionEngine(personality=Personality(extraversion=0.0))
        
        engine_extravert.register_event("joy", p_delta=0.5, a_delta=0.2, d_delta=0.0)
        engine_introvert.register_event("joy", p_delta=0.5, a_delta=0.2, d_delta=0.0)
        
        engine_extravert.trigger_event(["joy"])
        engine_introvert.trigger_event(["joy"])
        
        self.assertGreater(engine_extravert.state.pleasure, engine_introvert.state.pleasure, 
                           "Dışadönük karakter pozitif olaylara daha yüksek tepki vermelidir.")

    def test_clipping(self):
        # Sınırların ( -1.0 ile 1.0 ) aşılmadığından emin ol
        for _ in range(20):
            self.engine.trigger_event(["positive_event"])
            
        self.assertLessEqual(self.engine.state.pleasure, 1.0)
        self.assertGreaterEqual(self.engine.state.pleasure, -1.0)

    def test_esp32_state_output(self):
        # State: NEUTRAL
        state, intensity, desc = self.engine.get_esp32_state()
        self.assertEqual(state, "NEUTRAL")
        
        # State: HAPPY
        self.engine.state.pleasure = 0.8
        self.engine.state.arousal = 0.4
        state, intensity, desc = self.engine.get_esp32_state()
        self.assertEqual(state, "HAPPY")
        
        # State: SAD
        self.engine.state.pleasure = -0.8
        self.engine.state.arousal = -0.4
        state, intensity, desc = self.engine.get_esp32_state()
        self.assertEqual(state, "SAD")

if __name__ == '__main__':
    unittest.main()
