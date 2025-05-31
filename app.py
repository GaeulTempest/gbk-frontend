import json, threading, asyncio, time, urllib.parse, requests, av, websockets, mediapipe as mp
import streamlit as st
from streamlit_webrtc import webrtc_streamer, WebRtcMode, VideoProcessorBase
from gesture_utils import RPSMove, GestureStabilizer, _classify_from_landmarks

API = "https://web-production-7e17f.up.railway.app"
WS_PING = 20
AUTO_SUBMIT_DELAY = 5  # detik gesture stabil sebelum auto-submit

st.set_page_config("RPS Gesture Game", "✊")
st.title("✊ Rock-Paper-Scissors Online")

# ── Inisialisasi session_state ─────────────────────────
defaults = dict(
    game_id=None, player_id=None, role=None, player_name=None,
    players={}, _hash="", ws_thread=False, err=None,
    move_ts=0, detected_move=None, move_sent=False,
    game_started=False, gesture_stabilizer=GestureStabilizer(),
    camera_active=False, force_camera_key=0, camera_ctx=None
)
for k, v in defaults.items():
    st.session_state.setdefault(k, v)

# Inisialisasi MediaPipe Hands
if 'hands' not in st.session_state:
    st.session_state.hands = mp.solutions.hands.Hands(
        static_image_mode=False,
        max_num_hands=1,
        min_detection_confidence=0.5,
        min_tracking_confidence=0.5
    )

# ── Helper Functions ──────────────────────────────────
def post(path, **data):
    try:
        r = requests.post(f"{API}{path}", json=data, timeout=15)
        r.raise_for_status()
        return r.json()
    except requests.RequestException as e:
        st.session_state.err = e.response.text if e.response else str(e)

def get_state(gid):
    try:
        r = requests.get(f"{API}/state/{gid}", timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        st.session_state.err = f"Failed to get state: {str(e)}"

def _h(pl): return json.dumps(pl, sort_keys=True)

def set_players(pl):
    if _h(pl) != st.session_state._hash:
        st.session_state.players = pl
        st.session_state._hash = _h(pl)

# =========================================================
#  LOBBY TAB
# =========================================================
with st.sidebar:
    st.header("Lobby Settings")
    name = st.text_input("Your name", max_chars=20).strip()
    if name:
        st.session_state.player_name = name
    
    if not st.session_state.player_name:
        st.warning("Enter your name to continue.")
        st.stop()

    # Create/Join Room
    room = st.text_input("Room ID").strip()
    c1, c2 = st.columns(2)
    
    # Tombol untuk membuat room
    with c1:
        if st.button("Create Room") and name:
            try:
                # Panggil API untuk membuat game
                res = post("/create_game", player_name=name)
                if res:
                    # Update session_state dengan data game yang diterima dari backend
                    st.session_state.game_id = res["game_id"]
                    st.session_state.player_id = res["player_id"]
                    st.session_state.role = res["role"]
                    
                    # Tampilkan informasi Room ID dan status sukses
                    st.success(f"Game created successfully! Room ID: {res['game_id']}")
                    st.write(f"Your Player ID: {res['player_id']}")
                    st.write(f"Your Role: {res['role']}")
            except Exception as e:
                st.error(f"Failed to create game: {e}")

    # Tombol untuk bergabung ke room
    with c2:
        if st.button("Join Room") and room and name:
            try:
                res = post(f"/join/{room}", player_name=name)
                if 'error' in res:
                    st.error("Room ID tidak ditemukan.")
                elif res:
                    st.session_state.update(res)
            except Exception as e:
                st.error(f"Failed to join room: {e}")
