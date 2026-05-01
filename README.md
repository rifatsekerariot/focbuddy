# Focus Buddy

Focus Buddy is an interactive companion device that tracks your facial expressions and head movements in real-time, and mimics them on a small ESP32-powered OLED display using realistic, Cozmo-style animated eyes.

## Features
- **Real-Time Facial Tracking:** Uses Google's MediaPipe Face Landmarker (Tasks API) to detect head orientation (Pitch/Yaw) and 52 different facial blendshapes.
- **Emotion Recognition:** Accurately detects emotions and states such as:
  - Looking Left / Right / Up / Down
  - Happy (Smiling)
  - Sad (Frowning)
  - Talking (Jaw open)
  - Away (Face not detected)
- **Smooth BLE Communication:** State transitions are debounced and smoothly transmitted over Bluetooth Low Energy (BLE) to prevent flickering.
- **Realistic OLED Animations:** The ESP32 drives an I2C OLED display using the `u8g2` library and a custom procedural animation engine to render expressive eyes that dynamically change shape, blink, and move.

## Project Structure
- `pc_tracker/`: Contains the Python computer vision application.
  - `main.py`: The main tracking script that captures webcam feed, processes it using MediaPipe, and broadcasts the state via BLE.
  - `requirements.txt`: Python dependencies.
- `esp32_eyes/`: Contains the ESP32 C++ firmware.
  - `esp32_eyes.ino`: The main Arduino sketch.
  - `Face.h`, `Eye.h`, etc.: The C++ classes for rendering the procedural eyes (adapted from playfultechnology/esp32-eyes).

## Requirements

### Hardware
- ESP32 or ESP32-C3 microcontroller with Bluetooth support.
- 128x64 I2C OLED Display (SSD1306 or similar).
- A webcam connected to your PC.

### Software (PC)
- Python 3.8+
- Install dependencies: `pip install -r pc_tracker/fucbody/requirements.txt`
- (Note: `face_landmarker.task` model will be automatically downloaded on first run).

### Software (ESP32)
- Arduino IDE with ESP32 board support installed.
- **U8g2** library by `olikraus` (Install via Arduino Library Manager).
- ESP32 BLE Arduino libraries (built-in).

## How to Run
1. Flash the `esp32_eyes` sketch to your ESP32 board.
2. Ensure your PC's Bluetooth is enabled.
3. Run the python tracker script:
   ```bash
   python pc_tracker/fucbody/main.py
   ```
4. The tracker will connect to the ESP32 automatically and the eyes on the OLED screen will start mimicking your facial expressions!
