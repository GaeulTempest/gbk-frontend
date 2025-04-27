import streamlit as st
import cv2
from streamlit_webrtc import webrtc_streamer, VideoTransformerBase
import mediapipe as mp
import av

# Setup MediaPipe
mp_hands = mp.solutions.hands

# WebRTC Streamlit Transformer
class HandTrackingTransformer(VideoTransformerBase):
    def __init__(self):
        self.hands = mp_hands.Hands(static_image_mode=False, max_num_hands=1)
        self.mp_draw = mp.solutions.drawing_utils

    def transform(self, frame):
        img = frame.to_ndarray(format="bgr24")
        img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

        results = self.hands.process(img_rgb)

        if results.multi_hand_landmarks:
            for hand_landmarks in results.multi_hand_landmarks:
                self.mp_draw.draw_landmarks(img, hand_landmarks, mp_hands.HAND_CONNECTIONS)

        return av.VideoFrame.from_ndarray(img, format="bgr24")

# Streamlit Frontend
st.title("🖐️ Tes Handtracking Streamlit")

webrtc_streamer(
    key="handtracking",
    video_processor_factory=HandTrackingTransformer,
    media_stream_constraints={"video": True, "audio": False}
)
