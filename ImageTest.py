import cv2
import numpy as np
import requests
import urllib.request
import mediapipe as mp
from PIL import Image
from transformers import pipeline
from google.colab.patches import cv2_imshow

# ==========================================
# MODEL INITIALIZATION
# ==========================================

url_model = "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task"
urllib.request.urlretrieve(url_model, "hand_landmarker.task")


# MediaPipe Tasks
BaseOptions = mp.tasks.BaseOptions
HandLandmarker = mp.tasks.vision.HandLandmarker
HandLandmarkerOptions = mp.tasks.vision.HandLandmarkerOptions
VisionRunningMode = mp.tasks.vision.RunningMode

options = HandLandmarkerOptions(
    base_options=BaseOptions(model_asset_path='hand_landmarker.task'),
    running_mode=VisionRunningMode.IMAGE,
    num_hands=2
)
detector = HandLandmarker.create_from_options(options)

# depth
depth_pipe = pipeline(task="depth-estimation", model="Intel/dpt-hybrid-midas")

# ==========================================
# SENSITIVITY SETUP
# ==========================================
TOO_CLOSE_THRESHOLD = 200 # (0-255). The more, the closer an obstacle needs to be.
OBSTACLE_MIN_AREA_PERCENT = 0.05 # Obstacle needs to cover at least 5% of the screen to avoid noise.
IGNORE_FLOOR_PERCENT = 0.30 # Cuts % of picture at the bottom to ignore the floor

# ==========================================
# GESTURE FUNCTION
# ==========================================
def get_command_from_hand(hand_landmarks):
    fingers_up = 0
    # thumb
    #if abs(hand_landmarks[4].x - hand_landmarks[2].x) > abs(hand_landmarks[3].x - hand_landmarks[2].x): fingers_up += 1
    # pointing
    if hand_landmarks[8].y < hand_landmarks[6].y: fingers_up += 1
    # middle
    if hand_landmarks[12].y < hand_landmarks[10].y: fingers_up += 1
    # ring
    if hand_landmarks[16].y < hand_landmarks[14].y: fingers_up += 1
    # pinky
    if hand_landmarks[20].y < hand_landmarks[18].y: fingers_up += 1

    if fingers_up == 1: return "FORWARD"
    elif fingers_up == 2: return "BACKWARD"
    elif fingers_up == 3: return "LEFT"
    elif fingers_up == 4: return "RIGHT"
    else: return "NO_FINGERS"

# ==========================================
# TEST LINKS
# ==========================================
test_urls = [
    "https://raw.githubusercontent.com/Szymon-altJ/Humanoid-Legs---Zurych-Hackaton/main/2dal.jpg",
    "https://raw.githubusercontent.com/Szymon-altJ/Humanoid-Legs---Zurych-Hackaton/main/5dal.jpg",
    "https://raw.githubusercontent.com/Szymon-altJ/Humanoid-Legs---Zurych-Hackaton/main/3dal.jpg",
    "https://raw.githubusercontent.com/Szymon-altJ/Humanoid-Legs---Zurych-Hackaton/main/0dal.jpg",
    "https://raw.githubusercontent.com/Szymon-altJ/Humanoid-Legs---Zurych-Hackaton/main/dwa.jpg",
    "https://raw.githubusercontent.com/Szymon-altJ/Humanoid-Legs---Zurych-Hackaton/main/cztery.jpg",
    "https://raw.githubusercontent.com/Szymon-altJ/Humanoid-Legs---Zurych-Hackaton/main/przod2v2.jpg",
]

for i, url in enumerate(test_urls):
    print(f"\n{'='*40}")
    print(f"--- loading image {i+1} ---")

    # 1. loading image
    try: 
        response = requests.get(url)
        image_array = np.asarray(bytearray(response.content), dtype=np.uint8)
        img_cv2 = cv2.imdecode(image_array, cv2.IMREAD_COLOR)
    except Exception as e:
        print(f"Loading error: {e}")
        continue

    if img_cv2 is None: continue

    img_rgb = cv2.cvtColor(img_cv2, cv2.COLOR_BGR2RGB)
    h, w, _ = img_cv2.shape
    img_output = img_cv2.copy()

    # ==========================================
    # 2. DEPTH ESTIMATION AND OBSTACLE DETECTION
    # ==========================================
    pil_image = Image.fromarray(img_rgb)
    depth_result = depth_pipe(pil_image)
    depth_map = np.array(depth_result["depth"])
    depth_map_resized = cv2.resize(depth_map, (w, h))

    # Area we take into account (cutting floor at the bottom)
    roi_h = int(h * (1.0 - IGNORE_FLOOR_PERCENT))
    roi_depth_map = depth_map_resized[0:roi_h, :]

    # searching for px, which are too close (depth > TOO_CLOSE_THRESHOLD)
    close_pixels_mask = cv2.inRange(roi_depth_map, TOO_CLOSE_THRESHOLD, 255)
    close_pixels_count = cv2.countNonZero(close_pixels_mask)

    # Logic: is this amount of close pixels enough?
    min_pixels_for_obstacle = int((w * roi_h) * OBSTACLE_MIN_AREA_PERCENT)
    emergency_stop_signal = close_pixels_count > min_pixels_for_obstacle

    # ==========================================
    # 3. GESTURE DETECTION
    # ==========================================
    mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=img_rgb)
    detection_result = detector.detect(mp_image)

    movement_command = "NO_HAND_DETECTED"

    if detection_result.hand_landmarks:
        for hand_landmarks in detection_result.hand_landmarks:
            movement_command = get_command_from_hand(hand_landmarks)

            # drawing points on hand
            for landmark in hand_landmarks:
                cx, cy = int(landmark.x * w), int(landmark.y * h)
                cv2.circle(img_output, (cx, cy), 5, (255, 0, 0), -1)
            break # only one hand

    # ==========================================
    # 4. LOGIC AND VISUALIZATION
    # ==========================================
    # visualisation of gesture signal
    cv2.putText(img_output, f"GESTURE: {movement_command}", (20, 40),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 0), 2)

    # visualisation of obstacle alert
    if emergency_stop_signal:
        cv2.putText(img_output, "OBSTACLE: DETECTED", (20, 80),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 3)
    else:
        cv2.putText(img_output, "OBSTACLE: NOT DETECTED", (20, 80),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)

    # Adding line for cutting floor
    cv2.line(img_output, (0, roi_h), (w, roi_h), (255, 0, 255), 2)
    cv2.putText(img_output, "IGNORED FLOOR", (10, h - 20), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 0, 255), 2)

    # view with obstacle mask
    depth_colormap = cv2.applyColorMap(depth_map_resized, cv2.COLORMAP_INFERNO)

    # red colour for detected close obstacles
    mask_full = np.zeros_like(depth_map_resized)
    mask_full[0:roi_h, :] = close_pixels_mask
    depth_colormap[mask_full == 255] = [0, 0, 255] # red for obstacle

    #  conecting views
    combined_view = np.hstack((img_output, depth_colormap))
    cv2_imshow(combined_view)