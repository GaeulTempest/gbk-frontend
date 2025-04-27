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

if "camera_stop_request" not in st.session_state:
    st.session_state.camera_stop_request = False

if "force_rerun" not in st.session_state:
    st.session_state.force_rerun = False

# Timer
elapsed_time = int(time.time() - st.session_state.start_time)
remaining_time = 30 - elapsed_time

# Auto refresh untuk timer
if not st.session_state.gesture_submitted and not st.session_state.camera_stop_request:
    st_autorefresh(interval=1000, limit=None, key="timer_refresh")

# Progress bar
progress = st.progress(0)

if remaining_time > 0:
    progress.progress((30 - remaining_time) / 30)
    if not st.session_state.camera_stop_request:
        st.info(f"⏳ Sisa waktu: {remaining_time} detik (Kamera Aktif)")
    else:
        st.info(f"⏸️ Kamera dimatikan otomatis setelah submit gesture.")
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
                    if elapsed > 2:
                        st.session_state.auto_gesture_ready = True
                        st.session_state.auto_gesture_move = gesture
                        st.session_state.force_rerun = True  # Minta rerun app
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

# --- PAKSA RERUN KETIKA GESTURE READY ---
if st.session_state.get("force_rerun", False):
    st.session_state.force_rerun = False
    st.experimental_rerun()

# --- DETEKSI DAN EKSEKUSI AUTO SUBMIT ---
if ctx and ctx.state.playing and st.session_state.get('auto_gesture_ready', False):
    try:
        response = requests.post(f"{BASE_URL}/submit", json={
            "player": st.session_state.get("player", "A"),
            "move": st.session_state.get("auto_gesture_move", "Tidak dikenali")
        })
        if response.status_code == 200:
            st.success(f"✅ Gesture '{st.session_state['auto_gesture_move']}' berhasil dikirim otomatis!")
            st.session_state.gesture_submitted = True
            st.session_state.auto_gesture_ready = False
            st.session_state.camera_stop_request = True  # Request stop kamera
    except Exception as e:
        st.error(f"🚨 Error auto-submit gesture: {e}")

# --- MATIKAN KAMERA SECARA OTOMATIS ---
if st.session_state.camera_stop_request:
    if ctx and ctx.state.playing:
        ctx.stop()

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
