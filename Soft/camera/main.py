import cv2
import numpy as np
import urllib.request
import mediapipe as mp
import os
import threading
import time
from flask import Flask, Response, jsonify

# ==========================================
# MODEL INITIALIZATION
# ==========================================
model_path = "hand_landmarker.task"
if not os.path.exists(model_path):
    print("Downloading MediaPipe hand landmarker model...")
    url_model = "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task"
    urllib.request.urlretrieve(url_model, model_path)

BaseOptions = mp.tasks.BaseOptions
HandLandmarker = mp.tasks.vision.HandLandmarker
HandLandmarkerOptions = mp.tasks.vision.HandLandmarkerOptions
VisionRunningMode = mp.tasks.vision.RunningMode

options = HandLandmarkerOptions(
    base_options=BaseOptions(model_asset_path=model_path),
    running_mode=VisionRunningMode.IMAGE,
    num_hands=2
)
detector = HandLandmarker.create_from_options(options)

def get_command_from_hand(hand_landmarks):
    fingers_up = 0
    if hand_landmarks[8].y < hand_landmarks[6].y: fingers_up += 1
    if hand_landmarks[12].y < hand_landmarks[10].y: fingers_up += 1
    if hand_landmarks[16].y < hand_landmarks[14].y: fingers_up += 1
    if hand_landmarks[20].y < hand_landmarks[18].y: fingers_up += 1

    if fingers_up == 0: return "STOP"
    elif fingers_up == 1: return "FORWARD"
    elif fingers_up == 2: return "BACKWARD"
    elif fingers_up == 3: return "LEFT"
    elif fingers_up == 4: return "RIGHT"
    else: return "NO_FINGERS"

# ==========================================
# GLOBAL VARIABLES FOR API EXPORT
# ==========================================
current_state = {
    "command": "NO_FINGERS",
    "obstacle_detected": False
}
state_lock = threading.Lock()

# ==========================================
# FLASK SERVER & CAMERA THREAD
# ==========================================
app = Flask(__name__)
current_frame = None
frame_lock = threading.Lock()

def process_camera():
    global current_frame, current_state

    # Bezpośrednie połączenie z /dev/video0
    cap = cv2.VideoCapture("tcp://127.0.0.1:8888/")
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 320)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 240)

    if not cap.isOpened():
        print("BLAD: Nie mozna otworzyc kamery!")
        return

    print("Kamera gotowa - czytanie przez OpenCV")

    while True:
        ret, frame = cap.read()
        if not ret or frame is None:
            time.sleep(0.01)
            continue

        img_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, _ = frame.shape
        img_output = frame.copy()
        
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=img_rgb)
        detection_result = detector.detect(mp_image)
        movement_command = "NO_FINGERS"

        if detection_result.hand_landmarks:
            for hand_landmarks in detection_result.hand_landmarks:
                movement_command = get_command_from_hand(hand_landmarks)
                for landmark in hand_landmarks:
                    cx, cy = int(landmark.x * w), int(landmark.y * h)
                    cv2.circle(img_output, (cx, cy), 5, (255, 0, 0), -1)
                break 

        with state_lock:
            current_state["command"] = movement_command
            current_state["obstacle_detected"] = False

        cv2.putText(img_output, f"GESTURE: {movement_command}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 2)

        with frame_lock:
            current_frame = img_output.copy()

def generate_frames():
    global current_frame
    while True:
        with frame_lock:
            if current_frame is None:
                continue
            ret, buffer = cv2.imencode('.jpg', current_frame)
            frame_bytes = buffer.tobytes()
        yield (b'--frame\r\n' b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
        time.sleep(0.05)

# ==========================================
# FLASK ENDPOINTS
# ==========================================
@app.route('/')
def video_feed():
    return Response(generate_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/status')
def get_status():
    with state_lock:
        return jsonify(current_state)

if __name__ == '__main__':
    t = threading.Thread(target=process_camera)
    t.daemon = True
    t.start()
    app.run(host='0.0.0.0', port=5000, threaded=True, use_reloader=False)