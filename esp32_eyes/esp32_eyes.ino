#include <Arduino.h>
#include <Wire.h>
#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLEUtils.h>
#include <BLE2902.h>

#include "Common.h" // u8g2 objesi icin
#include "Face.h"

// Yüz (Face) nesnesi
Face *face;

// --- BLE Ayarları ---
#define SERVICE_UUID        "4fafc201-1fb5-459e-8fcc-c5c9c331914b"
#define CHARACTERISTIC_UUID "beb5483e-36e1-4688-b7f5-ea07361b26a8"

BLEServer* pServer = NULL;
BLECharacteristic* pCharacteristic = NULL;
bool deviceConnected = false;
unsigned long lastBleMessageTime = 0;

// BLE Server Callbacks
class MyServerCallbacks: public BLEServerCallbacks {
    void onConnect(BLEServer* pServer) {
      deviceConnected = true;
      Serial.println("BLE: Cihaz baglandi!");
      face->Expression.GoTo_Normal();
      face->Look.LookAt(0, 0);
    }

    void onDisconnect(BLEServer* pServer) {
      deviceConnected = false;
      Serial.println("BLE: Cihaz koptu, tekrar yayin yapiliyor...");
      BLEDevice::startAdvertising();
      face->Expression.GoTo_Sleepy();
    }
};

// BLE Characteristic Callbacks (Gelen veriyi okuma)
class MyCallbacks: public BLECharacteristicCallbacks {
    void onWrite(BLECharacteristic *pChar) {
      String value = pChar->getValue();

      if (value.length() > 0) {
        Serial.print("BLE Veri Alindi: ");
        Serial.println(value);
        lastBleMessageTime = millis();

        // İfadelere ve Bakışlara Göre Cozmo Animasyonları
        if (value == "LOOKING_CENTER") {
          face->Look.LookAt(0, 0);
          face->Expression.GoTo_Normal();
        } else if (value == "LOOKING_LEFT") {
          face->Look.LookAt(1.0, 0); 
          face->Expression.GoTo_Normal();
        } else if (value == "LOOKING_RIGHT") {
          face->Look.LookAt(-1.0, 0);
          face->Expression.GoTo_Normal();
        } else if (value == "LOOKING_UP") {
          face->Look.LookAt(0, 1.0);
          face->Expression.GoTo_Normal();
        } else if (value == "LOOKING_DOWN") {
          face->Look.LookAt(0, -1.0);
          face->Expression.GoTo_Normal();
        } else if (value == "TALKING") {
          face->Look.LookAt(0, 0);
          face->Expression.GoTo_Focused(); // Konusurken odaklanmis gozler iyi durur
        } else if (value == "SAD") {
          face->Look.LookAt(0, 0);
          face->Expression.GoTo_Sad();
        } else if (value == "HAPPY") {
          face->Look.LookAt(0, 0);
          face->Expression.GoTo_Happy();
        } else if (value == "AWAY") {
          face->Look.LookAt(0, 0);
          face->Expression.GoTo_Sleepy();
        }
      }
    }
};

void setup() {
  Serial.begin(115200);
  Serial.println("Focus Buddy Basliyor...");

  // Yüz Nesnesini Oluştur (Bu işlem u8g2.begin() i de icerir)
  face = new Face(/* screenWidth = */ 128, /* screenHeight = */ 64, /* eyeSize = */ 40);
  
  // Varsayılan İfade (Bağlantı beklerken uykulu)
  face->Expression.GoTo_Sleepy();
  
  // Kütüphanenin kendi rastgele modlarını kapatalım, çünkü BLE'den biz kontrol edeceğiz
  face->RandomBehavior = false; 
  face->RandomLook = false;     
  // Otomatik göz kırpma kalsın, cihaza sürekli bir canlılık katar
  face->RandomBlink = true;     
  face->Blink.Timer.SetIntervalMillis(4000);

  // Başlangıç yazısı
  u8g2.clearBuffer();
  u8g2.setFont(u8g2_font_ncenB08_tr);
  u8g2.drawStr(10, 30, "BLE Bekleniyor...");
  u8g2.sendBuffer();
  delay(1000);

  // BLE Başlatma
  BLEDevice::init("FocusBuddy");
  pServer = BLEDevice::createServer();
  pServer->setCallbacks(new MyServerCallbacks());

  BLEService *pService = pServer->createService(SERVICE_UUID);

  pCharacteristic = pService->createCharacteristic(
                      CHARACTERISTIC_UUID,
                      BLECharacteristic::PROPERTY_READ   |
                      BLECharacteristic::PROPERTY_WRITE  |
                      BLECharacteristic::PROPERTY_NOTIFY |
                      BLECharacteristic::PROPERTY_INDICATE
                    );

  pCharacteristic->setCallbacks(new MyCallbacks());
  pCharacteristic->addDescriptor(new BLE2902());

  pService->start();

  BLEAdvertising *pAdvertising = BLEDevice::getAdvertising();
  pAdvertising->addServiceUUID(SERVICE_UUID);
  pAdvertising->setScanResponse(true);
  pAdvertising->setMinPreferred(0x06);  
  pAdvertising->setMinPreferred(0x12);
  BLEDevice::startAdvertising();
  
  Serial.println("BLE Yayini Basladi. Baglanti bekleniyor...");
}

void loop() {
  // Göz animasyonlarını sürekli güncelle (Interpolasyon ve hareketler)
  face->Update();
}
