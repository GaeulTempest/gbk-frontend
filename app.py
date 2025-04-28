import streamlit as st
import requests
import cv2
import av
import time
from streamlit_webrtc import webrtc_streamer, VideoTransformerBase
import mediapipe as mp

# URL backend
BASE_URL = "https://web-production-7e17f.up.railway.app"

# Set page config
st.set_page_config(page_title="Gunting Batu Kertas Online", page_icon="✌️")
st.title("✌️ Gunting Batu Kertas Online Multiplayer")

# Session State
if "standby" not in st.session_state:
    st.session_state.standby = False
if "gesture_sent" not in st.session_state:
    st.session_state.gesture_sent = False
if "result_shown" not in st.session_state:
    st.session_state.result_shown = False
if "result_data" not in st.session_state:
    st.session_state.result_data = None

# Fungsi Deteksi Gesture
def detect_gesture(hand_landmarks, handedness):
    fingers = []
    if handedness == "Right":
        fingers.append(1 if hand_landmarks.landmark[4].x < hand_landmarks.landmark[3].x else 0)
    else:
        fingers.append(1 if hand_landmarks.landmark[4].x > hand_landmarks.landmark[3].x else 0)
    for tip in [8, 12, 16, 20]:
        fingers.append(1 if hand_landmarks.landmark[tip].y < hand_landmarks.landmark[tip - 2].y else 0)

    total_fingers = sum(fingers)

    if total_fingers == 0:
        return "Batu"
    elif total_fingers == 2 and fingers[1] and fingers[2] and not fingers[3] and not fingers[4]:
        return "Gunting"
    elif total_fingers == 5:
        return "Kertas"
    else:
        return "Tidak dikenali"

# Video Processor
class VideoProcessor(VideoTransformerBase):
    def __init__(self):
        self.gesture = "Belum ada"
        self.mp_hands = mp.solutions.hands
        self.hands = self.mp_hands.Hands(static_image_mode=False, max_num_hands=1, min_detection_confidence=0.7)
        self.mp_draw = mp.solutions.drawing_utils
        self.handedness = None

    def recv(self, frame):
        img = frame.to_ndarray(format="bgr24")
        img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        results = self.hands.process(img_rgb)

        if results.multi_hand_landmarks and results.multi_handedness:
            hand_landmarks = results.multi_hand_landmarks[0]
            self.handedness = results.multi_handedness[0].classification[0].label
