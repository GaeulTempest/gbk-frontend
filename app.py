import streamlit as st
from streamlit_webrtc import webrtc_streamer, VideoTransformerBase
import cv2
import requests
from gesture_utils import get_finger_count
import av
import time
from streamlit_autorefresh import st_autorefresh

BASE_URL = "https://web-production-7e17f.up.railway.app"

st.title("🕹️ Gunting Batu Kertas - ONLINE")

player = st.selectbox("Pilih peran", ["A", "B"])

# Timer setup
if "start_time" not in st.session_state:
    st.session_state.start_time = time.time()

# Hitung mundur
elapsed_time = int(time.time() - st.session_state.start_time)
remaining_time = 30 - elapsed_time

# Auto refresh tiap 1 detik selama masih ada waktu
if remaining_time > 0:
    st_autorefresh(interval=1000, limit=None, key="timer_refresh")

# Progress bar
progress = st.progress(0)
if remaining_time > 0:
    progress.progress((30 - remaining_time) / 30)
    st.info(f"⏳ Sisa waktu: {remaining_time} detik")
else:
    progress.progress(1.0)
    st.error("⏰ Waktu habis! Silakan refresh halaman untuk memulai ulang.")
    st.stop()  # Hentikan semua interaksi tanpa error

gesture_result = st.empty()

# Kamera WebRTC
class VideoProcessor(VideoTransformerBase):
    def __init__(self):
        self.gesture = None

    def transform(self, frame):
        img = frame.to_ndarray(format="bgr24")
        gesture, processed = get_finger_count(img)

        if gesture:
            cv2.putText(processed, f"{gesture}", (30, 60),
                        cv2.FONT_HERSHEY_SIMPLEX, 2, (0, 255, 0), 3)
            self.gesture = gesture

        return processed

ctx = webrtc_streamer(
    key="gbk",
    video_processor_factory=VideoProcessor,
    media_stream_constraints={"video": True, "audio": False}
)

# Tombol Kirim Gesture
if st.button("📤 Kirim Gerakan"):
    gesture = ctx.video_processor.gesture if ctx.video_processor else None
    if gesture in ["Batu", "Gunting", "Kertas"]:
        try:
            requests.post(f"{BASE_URL}/submit", json={"player": player, "move": gesture})
            st.success(f"Gerakan '{gesture}' dikirim sebagai Player {player}")
        except Exception as e:
            st.error(f"Error mengirim ke server: {e}")
    else:
        st.warning("Gesture belum dikenali")

# Tombol Lihat Hasil
if st.button("📊 Lihat Hasil"):
    try:
        res = requests.get(f"{BASE_URL}/result").json()
        if "result" in res:
            st.write(f"🧍 Player A: {res['A']} | 🧍 Player B: {res['B']}")
            st.success(f"🏆 Hasil: {res['result']}")
        else:
            st.warning("Menunggu lawan bermain...")
    except:
        st.error("Gagal terhubung ke server.")
