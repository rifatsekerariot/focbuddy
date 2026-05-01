import sqlite3
import time
from datetime import datetime
import os

class FocusDatabase:
    def __init__(self, db_path="focus_history.db"):
        self.db_path = db_path
        self._init_db()
        self.current_session_id = None
        self.session_start_time = None

    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                start_time DATETIME,
                end_time DATETIME,
                duration_seconds REAL
            )
        ''')
        conn.commit()
        conn.close()

    def start_session(self):
        if self.session_start_time is not None:
            return # Zaten aktif bir seans var
            
        self.session_start_time = time.time()
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        start_dt = datetime.now()
        cursor.execute('INSERT INTO sessions (start_time) VALUES (?)', (start_dt,))
        self.current_session_id = cursor.lastrowid
        conn.commit()
        conn.close()

    def end_session(self):
        if self.session_start_time is None or self.current_session_id is None:
            return
            
        duration = time.time() - self.session_start_time
        # Çok kısa seansları kaydetme (örn 10 saniyeden kısa)
        if duration > 10.0:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            end_dt = datetime.now()
            cursor.execute('''
                UPDATE sessions 
                SET end_time = ?, duration_seconds = ? 
                WHERE id = ?
            ''', (end_dt, duration, self.current_session_id))
            conn.commit()
            conn.close()
        
        self.session_start_time = None
        self.current_session_id = None

    def get_average_focus_time(self) -> float:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT AVG(duration_seconds) FROM sessions WHERE duration_seconds IS NOT NULL AND duration_seconds > 60')
        result = cursor.fetchone()[0]
        conn.close()
        return result if result else 0.0

class AutonomousBehavior:
    def __init__(self, db: FocusDatabase):
        self.db = db
        
        # Zaman Takibi
        self.last_face_time = 0
        self.is_user_present = False
        
        self.staring_start_time = 0
        self.is_staring = False
        
        # Otonom override statüsü
        self.override_emotion = None
        self.override_timeout = 0

    def update(self, face_detected: bool, current_time: float) -> str:
        """
        Kullanıcının varlığını takip eder ve gerekiyorsa otonom bir "Emotion Override" stringi döner.
        Yoksa None döner.
        """
        # --- Override süresi dolduysa temizle ---
        if self.override_emotion and current_time > self.override_timeout:
            self.override_emotion = None
            
        # --- Seans (Session) ve Varlık Takibi ---
        if face_detected:
            if not self.is_user_present:
                # Kullanıcı masaya oturdu / kameraya geldi -> Seansı başlat
                self.is_user_present = True
                self.staring_start_time = current_time
                self.db.start_session()
                
                # Yeni geldiğinde ufak bir selamlama
                self.override_emotion = "HAPPY"
                self.override_timeout = current_time + 3.0
                
            self.last_face_time = current_time
            
            # --- Staring (Gözetleme/Dik Dik Bakma) Kontrolü ---
            staring_duration = current_time - self.staring_start_time
            # 20 saniye kesintisiz bakıyorsa rahatsız/şüpheli hisseder
            if staring_duration > 20.0 and not self.is_staring:
                self.is_staring = True
                self.override_emotion = "SUSPICIOUS"
                self.override_timeout = current_time + 4.0
        else:
            if self.is_user_present:
                away_duration = current_time - self.last_face_time
                
                if away_duration > 5.0: # 5 saniye yüz yoksa gitmiş say ve seansı kapat
                    self.is_user_present = False
                    self.is_staring = False
                    self.db.end_session()
                    
            else:
                # Kullanıcı yokken geçen zaman
                away_duration = current_time - self.last_face_time
                
                # Eğer 60 saniyedir yoksa ve tam saniye dilimlerindeyse (sıkılma eylemleri)
                if away_duration > 60.0:
                    # Her 30 saniyede bir sıkıldığını/bıktığını gösterir
                    # int kullanımı basit bir zamanlayıcı oluşturur
                    time_int = int(current_time)
                    if time_int % 30 == 0 and not self.override_emotion:
                        self.override_emotion = "FRUSTRATED"
                        self.override_timeout = current_time + 5.0
                    # Veya daha da uzun sürdüyse umursamaz ifade takınır
                    elif time_int % 45 == 0 and not self.override_emotion:
                        self.override_emotion = "UNIMPRESSED"
                        self.override_timeout = current_time + 5.0

        return self.override_emotion
        
    def reset_staring(self, current_time: float):
        """Kullanıcı hareket ettiğinde (mimik vb) staring resetlenir, yani robot rahatlar."""
        self.staring_start_time = current_time
        self.is_staring = False
