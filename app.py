import streamlit as st
import cv2
import av
import time
import requests
from streamlit_webrtc import webrtc_streamer, VideoTransformerBase
import mediapipe as mp

BASE_URL = "https://web-production-7e17f.up.railway.app"

st.title("🕹️ Gunting Batu Kertas - ONLINE")

# --- PILIHAN PLAYER ---
player = st.selectbox("Pilih peran", ["A", "B"])
st.session_state.player = player

# --- SETUP session_state ---
if "start_time" not in st.session_state:
    st.session_state.start_time = time.time()

if "gesture_submitted" not in st.session_state:
    st.session_state.gesture_submitted = False

if "detected_gesture" not in st.session_state:
    st.session_state.detected_gesture = None

if "gesture_start_time" not in st.session_state:
    st.session_state.gesture_start_time = None

# --- TIMER DAN PROGRESS ---
elapsed_time = int(time.time() - st.session_state.start_time)
remaining_time = 30 - elapsed_time
progress = st.progress(0)

if remaining_time > 0:
    progress.progress((30 - remaining_time) / 30)
    st.info(f"⏳ Sisa waktu: {remaining_time} detik")
else:
    progress.progress(1.0)
    st.error("⏰ Waktu habis!")
    st.warning("Klik tombol di bawah ini untuk memulai ulang game.")
    if st.button("🔄 Main Lagi"):
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.experimental_rerun()
    st.stop()

gesture_result = st.empty()

# --- VideoProcessor Class pakai recv() ---
class VideoProcessor(VideoTransformerBase):
    def __init__(self):
        self.gesture = None
        self.mp_hands = mp.solutions.hands
        self.hands = self.mp_hands.Hands(static_image_mode=False, max_num_hands=1)
        self.mp_draw = mp.solutions.drawing_utils

    def recv(self, frame):
        img = frame.to_ndarray(format="bgr24")
        img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

        results = self.hands.process(img_rgb)
        gesture = None

        if results.multi_hand_landmarks:
            for hand_landmarks in results.multi_hand_landmarks:
                self.mp_draw.draw_landmarks(img, hand_landmarks, self.mp_hands.HAND_CONNECTIONS)

            # Gesture logic sederhana
            hand = results.multi_hand_landmarks[0]
            count = 0

            # Thumb
            if hand.landmark[4].x < hand.landmark[3].x:
                count += 1
            # 4 Fingers
            for tip in [8, 12, 16, 20]:
                if hand.landmark[tip].y < hand.landmark[tip - 2].y:
                    count += 1

            if count == 0:
                gesture = "Batu"
            elif count == 2:
                gesture = "Gunting"
            elif count == 5:
                gesture = "Kertas"
            else:
                gesture = "Tidak dikenali"

        self.gesture = gesture

        return av.VideoFrame.from_ndarray(img, format="bgr24")

# --- WebRTC Streamer ---
ctx = webrtc_streamer(
    key="handtracking",
    video_processor_factory=VideoProcessor,
    media_stream_constraints={"video": True, "audio": False}
)

# --- LOGIKA AUTO-SUBMIT ---
if ctx and ctx.video_processor:
    gesture_now = ctx.video_processor.gesture

    if gesture_now in ["Batu", "Gunting", "Kertas"]:
        if st.session_state.detected_gesture == gesture_now:
            elapsed = time.time() - st.session_state.gesture_start_time
            if elapsed >= 2 and not st.session_state.gesture_submitted:
                try:
                    response = requests.post(f"{BASE_URL}/submit", json={
                        "player": st.session_state.get("player", "A"),
                        "move": gesture_now
                    })
                    if response.status_code == 200:
                        st.success(f"✅ Auto-submit sukses! Gerakan '{gesture_now}' dikirim otomatis!")
                        st.session_state.gesture_submitted = True
                        ctx.stop()
                except Exception as e:
                    st.error(f"🚨 Gagal auto-submit gesture: {e}")
        else:
            st.session_state.detected_gesture = gesture_now
            st.session_state.gesture_start_time = time.time()

# --- Tombol Manual Submit (Backup) ---
if not st.session_state.gesture_submitted and ctx and ctx.video_processor:
    if st.button("📤 Kirim Gerakan Manual"):
        gesture = ctx.video_processor.gesture
        if gesture in ["Batu", "Gunting", "Kertas"]:
            try:
                response = requests.post(f"{BASE_URL}/submit", json={"player": player, "move": gesture})
                if response.status_code == 200:
                    st.success(f"✅ Gerakan '{gesture}' berhasil dikirim manual!")
                    st.session_state.gesture_submitted = True
                    ctx.stop()
            except Exception as e:
                st.error(f"🚨 Error kirim gesture manual: {e}")
        else:
            st.warning("✋ Gesture belum dikenali. Pastikan tanganmu terlihat jelas.")

# --- Tombol Lihat Hasil Pertandingan ---
if st.button("📊 Lihat Hasil"):
    try:
        res = requests.get(f"{BASE_URL}/result").json()
        if "result" in res:
            st.write(f"🧍 Player A: {res['A']} | 🧍 Player B: {res['B']}")
            st.success(f"🏆 Hasil: {res['result']}")
        else:
            st.warning("Menunggu lawan bermain...")
    except Exception as e:
        st.error(f"Error mengambil hasil dari server: {e}")
