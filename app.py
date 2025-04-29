import streamlit as st
import requests
import time
import cv2
import av
from streamlit_webrtc import webrtc_streamer, VideoTransformerBase
import mediapipe as mp
from collections import deque
import statistics

# Note: Ini adalah implementasi Multi-frame Stabilization untuk Gesture Detection

BASE_URL = "https://web-production-7e17f.up.railway.app"

# Setup page
st.set_page_config(page_title="✌️ Gunting Batu Kertas Online", page_icon="🎮")


# Styling
st.markdown("""
    <style>
    .title {font-size: 45px; color: #ff4b4b; text-align: center; font-weight: bold;}
    .subtitle {font-size: 25px; text-align: center; color: #1f77b4;}
    </style>
""", unsafe_allow_html=True)

st.markdown('<div class="title">Gunting Batu Kertas</div>', unsafe_allow_html=True)
st.markdown('<div class="subtitle">Multiplayer Online Game \ud83c\udfae</div>', unsafe_allow_html=True)

# Session states
if "gesture_sent" not in st.session_state:
    st.session_state.gesture_sent = False
if "result_shown" not in st.session_state:
    st.session_state.result_shown = False
if "result_data" not in st.session_state:
    st.session_state.result_data = None
if "countdown_started" not in st.session_state:
    st.session_state.countdown_started = False
if "manual_mode" not in st.session_state:
    st.session_state.manual_mode = False

# Gesture Detection
class GestureStabilizer:
    def __init__(self, max_frames=10):
        self.max_frames = max_frames
        self.gesture_queue = deque(maxlen=max_frames)

    def update(self, gesture):
        if gesture:
            self.gesture_queue.append(gesture)

    def get_stable_gesture(self):
        if not self.gesture_queue:
            return None
        try:
            stable = statistics.mode(self.gesture_queue)
            return stable
        except statistics.StatisticsError:
            return self.gesture_queue[-1]

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

class VideoProcessor(VideoTransformerBase):
    def __init__(self):
        self.gesture = "Belum ada"
        self.mp_hands = mp.solutions.hands
        self.hands = self.mp_hands.Hands(static_image_mode=False, max_num_hands=1, min_detection_confidence=0.7)
        self.mp_draw = mp.solutions.drawing_utils
        self.handedness = None
        self.stabilizer = GestureStabilizer(max_frames=10)  # <-- Multi-frame Stabilizer diaktifkan

    def recv(self, frame):
        img = frame.to_ndarray(format="bgr24")
        img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        results = self.hands.process(img_rgb)

        if results.multi_hand_landmarks and results.multi_handedness:
            hand_landmarks = results.multi_hand_landmarks[0]
            self.handedness = results.multi_handedness[0].classification[0].label
            self.mp_draw.draw_landmarks(img, hand_landmarks, self.mp_hands.HAND_CONNECTIONS)
            detected_gesture = detect_gesture(hand_landmarks, self.handedness)
            self.stabilizer.update(detected_gesture)
            stable_gesture = self.stabilizer.get_stable_gesture()
            if stable_gesture:
                self.gesture = stable_gesture
        else:
            self.stabilizer.update("Tidak dikenali")
            self.gesture = self.stabilizer.get_stable_gesture()

        return av.VideoFrame.from_ndarray(img, format="bgr24")

def reset_all_state():
    st.session_state.gesture_sent = False
    st.session_state.result_shown = False
    st.session_state.result_data = None
    st.session_state.countdown_started = False
    st.session_state.manual_mode = False

# Tabs
tabs = st.tabs(["\ud83d\ude80 Standby", "\ud83c\udfae Game"])

with tabs[0]:
    player = st.selectbox("Pilih peran kamu:", ["A", "B"])

    try:
        moves = requests.get(f"{BASE_URL}/get_moves").json()
    except Exception as e:
        st.error(f"\ud83d\udd0c Gagal ambil data server: {e}")
        moves = {}

    ready_players = []
    if moves.get("A_ready"):
        ready_players.append("Player A")
    if moves.get("B_ready"):
        ready_players.append("Player B")

    st.info(f"\ud83d\udc65 Pemain Standby: {', '.join(ready_players) if ready_players else 'Belum ada'}")

    player_ready_key = f"{player}_ready"
    if not moves.get(player_ready_key):
        if st.button("\ud83d\ude80 Klik Ready"):
            try:
                requests.post(f"{BASE_URL}/standby", json={"player": player})
                st.success("\u2705 Kamu sudah ready!")
            except Exception as e:
                st.error(f"\u274c Error standby: {e}")
    else:
        st.success("\u2705 Kamu sudah standby!")

with tabs[1]:
    try:
        moves = requests.get(f"{BASE_URL}/get_moves").json()
    except:
        moves = {}

    if st.session_state.result_shown:
        result = st.session_state.result_data
        winner = result["result"]
        move_a = result["A"]
        move_b = result["B"]

        if winner == "Seri":
            st.snow()
        else:
            st.balloons()

        st.success(f"\ud83c\udfc6 {winner}")
        st.info(f"\ud83c\udfae Player A: {move_a}\n\ud83c\udfae Player B: {move_b}")

        try:
            stats = requests.get(f"{BASE_URL}/stats").json()
            col1, col2 = st.columns(2)
            with col1:
                st.metric("\ud83c\udfc6 Player A Menang", stats["Player A"]["win"])
                st.metric("\u274c Player A Kalah", stats["Player A"]["lose"])
                st.metric("\ud83e\udd1d Player A Seri", stats["Player A"]["draw"])
            with col2:
                st.metric("\ud83c\udfc6 Player B Menang", stats["Player B"]["win"])
                st.metric("\u274c Player B Kalah", stats["Player B"]["lose"])
                st.metric("\ud83e\udd1d Player B Seri", stats["Player B"]["draw"])
        except:
            st.error("\u274c Gagal ambil statistik.")

        if st.button("\ud83d\udd04 Main Lagi"):
            try:
                requests.post(f"{BASE_URL}/reset")
                st.success("\u2705 Game direset, silakan Ready lagi.")
            except:
                st.error("\u274c Gagal reset game.")
            reset_all_state()
            st.rerun()

    else:
        if not (moves.get("A_ready") and moves.get("B_ready")):
            st.warning("\u23f3 Menunggu semua pemain Ready...")
        else:
            ctx = webrtc_streamer(
                key="handtracking",
                video_processor_factory=VideoProcessor,
                media_stream_constraints={"video": True, "audio": False}
            )

            if ctx and ctx.state.playing:
                if ctx.video_processor:
                    gesture_now = ctx.video_processor.gesture
                    st.success(f"\ud83d\udc50 Gesture terdeteksi: {gesture_now}")

                    if not st.session_state.gesture_sent:
                        if not st.session_state.countdown_started:
                            st.session_state.countdown_started = True

                        if st.session_state.countdown_started:
                            with st.spinner("\u231b Countdown 3 detik..."):
                                time.sleep(3)
                            if gesture_now in ["Batu", "Gunting", "Kertas"]:
                                try:
                                    requests.post(f"{BASE_URL}/submit", json={"player": player, "move": gesture_now})
                                    st.success(f"\u2705 Gerakan '{gesture_now}' berhasil dikirim otomatis!")
                                    st.session_state.gesture_sent = True
                                except:
                                    st.error("\u274c Gagal kirim otomatis.")
                            else:
                                st.warning("\u270b Gesture belum jelas. Gunakan tombol manual.")

                    if not st.session_state.gesture_sent:
                        if st.button("\ud83d\udce4 Kirim Manual"):
                            if gesture_now in ["Batu", "Gunting", "Kertas"]:
                                try:
                                    requests.post(f"{BASE_URL}/submit", json={"player": player, "move": gesture_now})
                                    st.success(f"\u2705 Gerakan '{gesture_now}' berhasil dikirim manual!")
                                    st.session_state.gesture_sent = True
                                except:
                                    st.error("\u274c Gagal kirim manual.")
                            else:
                                st.warning("\u270b Gesture belum jelas.")
            else:
                st.warning("\ud83d\udeab Kamera tidak aktif!")

            if st.session_state.gesture_sent and not st.session_state.result_shown:
                with st.spinner("\u23f3 Menunggu hasil pertandingan..."):
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
