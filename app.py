import cv2
import requests
import time
import streamlit as st
from gesture_utils import get_finger_count
from streamlit_webrtc import VideoTransformerBase

BASE_URL = "https://web-production-7e17f.up.railway.app"  # Pastikan ini sesuai backend

# Kamera WebRTC
class VideoProcessor(VideoTransformerBase):
    def __init__(self):
        self.gesture = None
        self.last_gesture = None
        self.gesture_start_time = None
        self.confirmed = False  # Untuk memastikan hanya kirim sekali

    def transform(self, frame):
        img = frame.to_ndarray(format="bgr24")
        gesture, processed = get_finger_count(img)

        if gesture:
            cv2.putText(processed, f"{gesture}", (30, 60),
                        cv2.FONT_HERSHEY_SIMPLEX, 2, (0, 255, 0), 3)
            self.gesture = gesture

            # Cek gesture stabil
            if gesture == self.last_gesture:
                # Gesture tidak berubah
                if self.gesture_start_time and not self.confirmed:
                    elapsed = time.time() - self.gesture_start_time
                    if elapsed > 5:  # 5 detik stabil
                        # Auto submit ke server
                        self.auto_submit_gesture()
                        self.confirmed = True  # Supaya hanya kirim sekali
            else:
                # Gesture berubah
                self.last_gesture = gesture
                self.gesture_start_time = time.time()
                self.confirmed = False

        return processed

    def auto_submit_gesture(self):
        try:
            player = st.session_state.get("player", "A")  # Pastikan player sudah dipilih
            response = requests.post(f"{BASE_URL}/submit", json={
                "player": player,
                "move": self.gesture
            })
            if response.status_code == 200:
                st.session_state.gesture_submitted = True
                st.success(f"✅ Gesture '{self.gesture}' dikonfirmasi otomatis sebagai Player {player} setelah 5 detik!")
            else:
                st.error(f"⚠️ Gagal auto-submit: {response.json().get('error', 'Unknown error')}")
        except Exception as e:
            st.error(f"🚨 Error auto-submit gesture: {e}")
