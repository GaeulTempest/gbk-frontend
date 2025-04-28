import streamlit as st
import cv2
import av
import time
import requests
from streamlit_webrtc import webrtc_streamer, VideoTransformerBase
import mediapipe as mp

BASE_URL = "https://web-production-7e17f.up.railway.app"  # Ganti sesuai alamat backend kamu

st.title("🕹️ Gunting Batu Kertas - ONLINE")

player = st.selectbox("Pilih peran", ["A", "B"])

# Session State Setup
if "standby" not in st.session_state:
    st.session_state.standby = False
if "game_started" not in st.session_state:
    st.session_state.game_started = False
if "start_time" not in st.session_state:
    st.session_state.start_time = None

# --- Fungsi Deteksi Gesture ---
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
            self.handedness = results.multi_handedness[0].classification[0].label
            self.mp_draw.draw_landmarks(img, hand_landmarks, self.mp_hands.HAND_CONNECTIONS)
            self.gesture = detect_gesture(hand_landmarks, self.handedness)
        else:
            self.gesture = "Tidak dikenali"

        return av.VideoFrame.from_ndarray(img, format="bgr24")

# --- Fungsi Reset Semua Session State ---
def reset_all_state():
    st.session_state.standby = False
    st.session_state.game_started = False
    st.session_state.start_time = None

# --- Check Siapa yang Standby ---
moves = requests.get(f"{BASE_URL}/get_moves").json()

ready_players = []
if moves.get("A_ready"):
    ready_players.append("Player A")
if moves.get("B_ready"):
    ready_players.append("Player B")

st.info(f"👥 Pemain yang sudah siap: {', '.join(ready_players) if ready_players else 'Belum ada'}")

# --- Tombol Standby ---
if not st.session_state.standby:
    if st.button("🚀 Standby Siap Main"):
        try:
            response = requests.post(f"{BASE_URL}/standby", json={"player": player})
            if response.status_code == 200:
                st.success("✅ Kamu sudah standby!")
                st.session_state.standby = True
            else:
                st.error("❌ Gagal standby.")
        except Exception as e:
            st.error(f"🚨 Error saat standby: {e}")

# --- Cek Semua Pemain Sudah Siap ---
if not (moves.get("A_ready") and moves.get("B_ready")):
    st.warning("⏳ Menunggu semua pemain standby...")
    st.stop()

# --- Mulai Game Setelah Siap ---
if not st.session_state.game_started:
    st.session_state.start_time = time.time()
    st.session_state.game_started = True

# --- Timer Progress 60 Detik ---
elapsed_time = int(time.time() - st.session_state.start_time)
remaining_time = 60 - elapsed_time
progress = st.progress(0)

if remaining_time > 0:
    progress.progress(elapsed_time / 60)
    st.info(f"⏳ Sisa waktu: {remaining_time} detik")
else:
    progress.progress(1.0)
    st.error("⏰ Waktu habis! Game selesai.")
    if st.button("🔄 Main Lagi"):
        requests.post(f"{BASE_URL}/reset")
        reset_all_state()
        st.rerun()
    st.stop()

# --- Stream Kamera ---
ctx = webrtc_streamer(
    key="handtracking",
    video_processor_factory=VideoProcessor,
    media_stream_constraints={"video": True, "audio": False}
)

# --- Deteksi Gesture dan Kirim Move ---
if ctx and ctx.state.playing:
    st.subheader("📸 Kamera Aktif!")
    if ctx.video_processor:
        gesture_now = ctx.video_processor.gesture
        st.success(f"🖐️ Gerakan Terdeteksi: **{gesture_now}**")

        if st.button("📤 Kirim Gerakan"):
            if gesture_now in ["Batu", "Gunting", "Kertas"]:
                try:
                    response = requests.post(f"{BASE_URL}/submit", json={"player": player, "move": gesture_now})
                    if response.status_code == 200:
                        st.success(f"✅ Gerakan '{gesture_now}' berhasil dikirim!")
                        st.info("✅ Menunggu hasil dari server...")
                        # ctx.state.playing = False  <-- HAPUS INI!!!
                    else:
                        st.error("❌ Gagal kirim gesture.")
                except Exception as e:
                    st.error(f"🚨 Error kirim gesture: {e}")
            else:
                st.warning("✋ Gesture belum dikenali.")
    else:
        st.warning("🔄 Mendeteksi gerakan...")
else:
    st.warning("🚫 Kamera belum aktif atau sudah berhenti.")

