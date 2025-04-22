import streamlit as st
from streamlit_webrtc import webrtc_streamer, VideoTransformerBase
import cv2
import requests
from gesture_utils import get_finger_count
import av

BASE_URL = "https://web-production-7e17f.up.railway.app"
st.title("🕹️ Gunting Batu Kertas - ONLINE")

player = st.selectbox("Pilih peran", ["A", "B"])
gesture_result = st.empty()

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

# Tombol kirim gesture
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

# Tombol lihat hasil
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
