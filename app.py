import streamlit as st
from streamlit_webrtc import webrtc_streamer, VideoTransformerBase
import cv2
import requests
import time
from gesture_utils import get_finger_count
from streamlit_autorefresh import st_autorefresh

BASE_URL = "https://web-production-7e17f.up.railway.app"

st.title("🕹️ Gunting Batu Kertas - ONLINE")

player = st.selectbox("Pilih peran", ["A", "B"])
st.session_state.player = player

# Setup session_state
if "start_time" not in st.session_state:
    st.session_state.start_time = time.time()

if "gesture_submitted" not in st.session_state:
    st.session_state.gesture_submitted = False

if "auto_gesture_ready" not in st.session_state:
    st.session_state.auto_gesture_ready = False

# Timer
elapsed_time = int(time.time() - st.session_state.start_time)
remaining_time = 30 - elapsed_time

if not st.session_state.gesture_submitted:
    st_autorefresh(interval=1000, limit=None, key="timer_refresh")

# Progress bar
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

# --- Kamera WebRTC dan Gesture Processor ---
class VideoProcessor(VideoTransformerBase):
    def __init__(self):
        self.gesture = None
        self.last_gesture = None
        self.gesture_start_time = None
        self.confirmed = False

    def transform(self, frame):
        img = frame.to_ndarray(format="bgr24")
        gesture, processed = get_finger_count(img)

        if gesture:
            cv2.putText(processed, f"{gesture}", (30, 60),
                        cv2.FONT_HERSHEY_SIMPLEX, 2, (0, 255, 0), 3)
            self.gesture = gesture

            if gesture == self.last_gesture:
                if self.gesture_start_time and not self.confirmed:
                    elapsed = time.time() - self.gesture_start_time
                    if elapsed > 2:  # hanya 2 detik untuk auto-submit
                        st.session_state.auto_gesture_ready = True
                        st.session_state.auto_gesture_move = gesture
                        self.confirmed = True
            else:
                self.last_gesture = gesture
                self.gesture_start_time = time.time()
                self.confirmed = False

        return processed

ctx = webrtc_streamer(
    key="gbk",
    video_processor_factory=VideoProcessor,
    media_stream_constraints={"video": True, "audio": False}
)

# --- Auto Submit Gesture jika sudah siap ---
if st.session_state.get('auto_gesture_ready', False):
    try:
        response = requests.post(f"{BASE_URL}/submit", json={
            "player": st.session_state.get("player", "A"),
            "move": st.session_state.get("auto_gesture_move", "Tidak dikenali")
        })
        if response.status_code == 200:
            st.success(f"✅ Gesture '{st.session_state['auto_gesture_move']}' dikirim otomatis setelah stabil 2 detik!")
            st.session_state.gesture_submitted = True
            st.session_state.auto_gesture_ready = False
        else:
            st.error(f"⚠️ Gagal auto-submit: {response.json().get('error', 'Unknown error')}")
    except Exception as e:
        st.error(f"🚨 Error auto-submit gesture: {e}")

# --- Tombol Kirim Gerakan Manual ---
if st.button("📤 Kirim Gerakan Manual"):
    gesture = ctx.video_processor.gesture if ctx.video_processor else None
    if gesture in ["Batu", "Gunting", "Kertas"]:
        try:
            response = requests.post(f"{BASE_URL}/submit", json={"player": player, "move": gesture})
            if response.status_code == 200:
                st.success(f"✅ Gesture '{gesture}' berhasil dikirim manual sebagai Player {player}!")
                st.session_state.gesture_submitted = True
            else:
                st.error(f"⚠️ Gagal mengirim: {response.json().get('error', 'Unknown error')}")
        except Exception as e:
            st.error(f"🚨 Error mengirim gesture manual: {e}")
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
