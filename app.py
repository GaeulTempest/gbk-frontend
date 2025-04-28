import streamlit as st
import cv2
import av
import time
import requests
from streamlit_webrtc import webrtc_streamer, VideoTransformerBase
import mediapipe as mp

BASE_URL = "https://web-production-7e17f.up.railway.app"  # Sesuaikan URL backend kamu

st.title("🕹️ Gunting Batu Kertas - ONLINE")

player = st.selectbox("Pilih peran", ["A", "B"])
st.session_state.player = player

# Status standby
if "standby" not in st.session_state:
    st.session_state.standby = False

# Tombol Standby
if not st.session_state.standby:
    if st.button("🚀 Standby Siap Main"):
        try:
            response = requests.post(f"{BASE_URL}/standby", json={"player": player})
            if response.status_code == 200:
                st.success("✅ Kamu sudah standby! Tunggu pemain lain...")
                st.session_state.standby = True
            else:
                st.error("❌ Gagal standby.")
        except Exception as e:
            st.error(f"🚨 Error saat standby: {e}")
    st.stop()  # Stop halaman disini dulu kalau belum standby

# Cek apakah kedua pemain sudah standby
status_info = requests.get(f"{BASE_URL}/result").json()
if "Menunggu pemain lain untuk standby" in status_info.get("status", ""):
    st.warning("⏳ Menunggu pemain lain untuk standby...")
    st.stop()

# --- Timer Progress Bar ---
if "start_time" not in st.session_state:
    st.session_state.start_time = time.time()

elapsed_time = int(time.time() - st.session_state.start_time)
remaining_time = 30 - elapsed_time
progress = st.progress(0)

if remaining_time > 0:
    progress.progress(elapsed_time / 30)
    st.info(f"⏳ Sisa waktu: {remaining_time} detik")
else:
    progress.progress(1.0)
    st.error("⏰ Waktu habis!")
    if st.button("🔄 Main Lagi"):
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        requests.post(f"{BASE_URL}/reset")
        st.experimental_rerun()
    st.stop()

# --- Fungsi Deteksi Gesture ---
def detect_gesture(hand_landmarks, handedness):
    fingers = []

    # Thumb
    if handedness == "Right":
        fingers.append(1 if hand_landmarks.landmark[4].x < hand_landmarks.landmark[3].x else 0)
    else:  # Left
        fingers.append(1 if hand_landmarks.landmark[4].x > hand_landmarks.landmark[3].x else 0)

    # 4 Fingers
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

# --- Video Processor ---
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
            self.handedness = results.multi_handedness[0].classification[0].label  # "Left" or "Right"
            self.mp_draw.draw_landmarks(img, hand_landmarks, self.mp_hands.HAND_CONNECTIONS)
            self.gesture = detect_gesture(hand_landmarks, self.handedness)
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
    if st.button("📤 Kirim Gerakan"):
        gesture = ctx.video_processor.gesture
        if gesture in ["Batu", "Gunting", "Kertas"]:
            try:
                response = requests.post(f"{BASE_URL}/submit", json={"player": player, "move": gesture})
                if response.status_code == 200:
                    st.success(f"✅ Gerakan '{gesture}' berhasil dikirim!")
                    ctx.state.playing = False
                else:
                    st.error("❌ Gagal kirim gerakan.")
            except Exception as e:
                st.error(f"🚨 Error kirim gesture: {e}")
        else:
            st.warning("✋ Gesture belum dikenali. Pastikan tanganmu terlihat jelas.")
