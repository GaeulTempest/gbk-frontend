import streamlit as st
import cv2
import av
import time
import requests
from streamlit_webrtc import webrtc_streamer, VideoTransformerBase
import mediapipe as mp

BASE_URL = "https://web-production-7e17f.up.railway.app"

st.title("🕹️ Gunting Batu Kertas - ONLINE")

player = st.selectbox("Pilih peran", ["A", "B"])
st.session_state.player = player

# --- Timer Progress Bar ---
if "start_time" not in st.session_state:
    st.session_state.start_time = time.time()

elapsed_time = int(time.time() - st.session_state.start_time)
remaining_time = 30 - elapsed_time
progress = st.progress(0)

if remaining_time > 0:
    progress.progress((30 - remaining_time) / 30)
    st.info(f"⏳ Sisa waktu: {remaining_time} detik")
else:
    progress.progress(1.0)
    st.error("⏰ Waktu habis!")
    if st.button("🔄 Main Lagi"):
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.experimental_rerun()
    st.stop()

# --- Fungsi Deteksi Gesture ---
def detect_gesture(hand_landmarks):
    fingers = []

    # Thumb
    if hand_landmarks.landmark[4].x < hand_landmarks.landmark[3].x:
        fingers.append(1)
    else:
        fingers.append(0)

    # 4 Fingers
    for tip, pip in [(8, 6), (12, 10), (16, 14), (20, 18)]:
        if hand_landmarks.landmark[tip].y < hand_landmarks.landmark[pip].y:
            fingers.append(1)
        else:
            fingers.append(0)

    total_fingers = sum(fingers)

    if total_fingers == 0:
        return "Batu"
    elif total_fingers == 2 and fingers[1] and fingers[2] and not fingers[3] and not fingers[4]:
        return "Gunting"
    elif total_fingers == 5:
        return "Kertas"
    else:
        return "Tidak dikenali"

# --- Video Processor pakai recv() ---
class VideoProcessor(VideoTransformerBase):
    def __init__(self):
        self.gesture = "Belum ada"
        self.mp_hands = mp.solutions.hands
        self.hands = self.mp_hands.Hands(static_image_mode=False, max_num_hands=1)
        self.mp_draw = mp.solutions.drawing_utils

    def recv(self, frame):
        img = frame.to_ndarray(format="bgr24")
        img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

        results = self.hands.process(img_rgb)

        if results.multi_hand_landmarks:
            for hand_landmarks in results.multi_hand_landmarks:
                self.mp_draw.draw_landmarks(img, hand_landmarks, self.mp_hands.HAND_CONNECTIONS)
                self.gesture = detect_gesture(hand_landmarks)
        else:
            self.gesture = "Tidak dikenali"

        return av.VideoFrame.from_ndarray(img, format="bgr24")

# --- Streamer ---
ctx = webrtc_streamer(
    key="handtracking",
    video_processor_factory=VideoProcessor,
    media_stream_constraints={"video": True, "audio": False}
)

# --- Tampilkan Gesture Secara Langsung ---
if ctx and ctx.state.playing:
    st.subheader("📸 Kamera Aktif!")
    if ctx.video_processor:
        gesture_now = ctx.video_processor.gesture
        st.success(f"🖐️ Gerakan Terdeteksi: **{gesture_now}**")
    else:
        st.warning("🔄 Mendeteksi gerakan...")
else:
    st.warning("🚫 Kamera belum aktif atau sudah berhenti.")

# --- Tombol Manual Submit ---
if ctx and ctx.video_processor:
    if st.button("📤 Kirim Gerakan Manual"):
        gesture = ctx.video_processor.gesture
        if gesture in ["Batu", "Gunting", "Kertas"]:
            try:
                response = requests.post(f"{BASE_URL}/submit", json={"player": player, "move": gesture})
                if response.status_code == 200:
                    st.success(f"✅ Gerakan '{gesture}' berhasil dikirim manual!")
                    ctx.state.playing = False  # <-- Ini yang bener, bukan ctx.stop()
            except Exception as e:
                st.error(f"🚨 Error kirim gesture manual: {e}")
        else:
            st.warning("✋ Gesture belum dikenali. Pastikan tanganmu terlihat jelas.")

