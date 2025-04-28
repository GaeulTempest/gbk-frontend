import streamlit as st
import requests
import cv2
import av
import time
from streamlit_webrtc import webrtc_streamer, VideoTransformerBase
import mediapipe as mp

# URL backend
BASE_URL = "https://web-production-7e17f.up.railway.app"

# Set page config
st.set_page_config(page_title="Gunting Batu Kertas Online", page_icon="✌️")
st.title("✌️ Gunting Batu Kertas Online Multiplayer")

# Session State
if "standby" not in st.session_state:
    st.session_state.standby = False
if "gesture_sent" not in st.session_state:
    st.session_state.gesture_sent = False
if "result_shown" not in st.session_state:
    st.session_state.result_shown = False
if "result_data" not in st.session_state:
    st.session_state.result_data = None

# Fungsi Deteksi Gesture
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

# Video Processor
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

# Reset Semua State
def reset_all_state():
    st.session_state.standby = False
    st.session_state.gesture_sent = False
    st.session_state.result_shown = False
    st.session_state.result_data = None

# Pilih Peran
player = st.selectbox("Pilih peran", ["A", "B"])

# Cek siapa yang standby
try:
    moves = requests.get(f"{BASE_URL}/get_moves").json()
except Exception as e:
    st.error(f"🔌 Gagal terhubung ke server: {e}")
    moves = {}

ready_players = []
if moves.get("A_ready"):
    ready_players.append("Player A")
if moves.get("B_ready"):
    ready_players.append("Player B")

st.info(f"👥 Pemain Standby: {', '.join(ready_players) if ready_players else 'Belum ada'}")

# Tombol Standby
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
            st.error(f"🚨 Error standby: {e}")

# Kalau belum dua pemain standby
if not (moves.get("A_ready") and moves.get("B_ready")):
    st.warning("⏳ Menunggu semua pemain standby...")
    # Tidak pakai st.stop(), supaya user tetap bisa standby
else:
    # Kalau sudah dua pemain standby ➔ lanjutkan game

    # Kamera Stream
    ctx = webrtc_streamer(
        key="handtracking",
        video_processor_factory=VideoProcessor,
        media_stream_constraints={"video": True, "audio": False}
    )

    # Main Game
    if ctx and ctx.state.playing:
        st.subheader("📸 Kamera Aktif - Deteksi Gesture")
        if ctx.video_processor:
            gesture_now = ctx.video_processor.gesture
            st.success(f"🖐️ Gesture Terdeteksi: **{gesture_now}**")

            if not st.session_state.gesture_sent:
                if st.button("📤 Kirim Gerakan"):
                    if gesture_now in ["Batu", "Gunting", "Kertas"]:
                        try:
                            response = requests.post(f"{BASE_URL}/submit", json={"player": player, "move": gesture_now})
                            if response.status_code == 200:
                                st.success(f"✅ Gerakan '{gesture_now}' berhasil dikirim!")
                                st.session_state.gesture_sent = True
                            else:
                                st.error("❌ Gagal kirim gesture.")
                        except Exception as e:
                            st.error(f"🚨 Error kirim gesture: {e}")
                    else:
                        st.warning("✋ Gesture belum dikenali.")
        else:
            st.warning("🔄 Mendeteksi gesture...")
    else:
        st.warning("🚫 Kamera belum aktif.")

    # Setelah Kirim Gesture: Tunggu hasil
    if st.session_state.gesture_sent and not st.session_state.result_shown:
        with st.spinner("⏳ Menunggu hasil pertandingan..."):
            while True:
                try:
                    result = requests.get(f"{BASE_URL}/result").json()
                    if "result" in result:
                        st.session_state.result_data = result
                        st.session_state.result_shown = True
                        break
                except:
                    pass
                time.sleep(2)
            st.rerun()

    # Menampilkan Hasil
    if st.session_state.result_shown and st.session_state.result_data:
        result = st.session_state.result_data
        winner = result["result"]
        move_a = result["A"]
        move_b = result["B"]

        st.balloons()
        st.success(f"🏆 {winner}!\n\n🎮 Player A: **{move_a}**\n🎮 Player B: **{move_b}**")

        if st.button("🔄 Main Lagi"):
            try:
                requests.post(f"{BASE_URL}/reset")
            except:
                pass
            reset_all_state()
            st.rerun()
