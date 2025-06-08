import json, threading, asyncio, time, urllib.parse, requests, av, websockets, mediapipe as mp
import streamlit as st
from streamlit_webrtc import webrtc_streamer, WebRtcMode, RTCConfiguration, VideoProcessorBase
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
    cam_ctx=None, game_started=False
)
for k, v in defaults.items():
    st.session_state.setdefault(k, v)

# ── Helper HTTP ────────────────────────────────────────
def post(path, **data):
    try:
        r = requests.post(f"{API}{path}", json=data, timeout=15)
        r.raise_for_status()
        return r.json()
    except requests.RequestException as e:
        st.session_state.err = (
            e.response.text if getattr(e, "response", None) else str(e)
        )

def get_state(gid):
    try:
        r = requests.get(f"{API}/state/{gid}", timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        st.session_state.err = f"Failed to get state: {str(e)}"
        return None

def get_stun_turn_config():
    try:
        response = requests.get(f"{API}/stun_turn_config", timeout=10)
        response.raise_for_status()  # Raise error if status code is not 2xx
        return response.json()
    except requests.RequestException as e:
        st.session_state.err = f"Failed to get STUN/TURN config: {str(e)}"
        st.warning("STUN/TURN configuration could not be retrieved. Ensure Xirsys API is working.")
        return None

# ── Ambil konfigurasi STUN/TURN dari server ─────────────────
stun_turn_config = get_stun_turn_config()

if stun_turn_config:
    ice_servers = stun_turn_config.get("iceServers", [])
    RTC_CONFIG = RTCConfiguration({
        "iceServers": ice_servers
    })
else:
    st.warning("STUN/TURN configuration could not be retrieved. Ensure Xirsys API is working.")

# =========================================================
#  LOBBY TAB
# =========================================================
tab_lobby, tab_game = st.tabs(["🏠 Lobby", "🎮 Game"])

with tab_lobby:
    st.subheader("Lobby: Create or Join Room")
    
    # Input Name
    name = st.text_input("Your name", max_chars=20).strip()
    if name:
        st.session_state.player_name = name

    if not st.session_state.player_name:
        st.warning("Please enter your name to continue.")
        st.stop()

    cA, cB = st.columns(2)

    # Create Room
    with cA:
        if st.button("Create Room"):
            res = post("/create_game", player_name=name)
            if res:
                st.session_state.update(res)
                st.session_state.game_started = False
                st.session_state.cam_ctx = None
                st.session_state.detected_move = None
                st.session_state.move_ts = 0
                st.session_state.move_sent = False
                st.success(f"Room Created! Your Game ID is: {st.session_state.game_id}")
            else:
                st.error(st.session_state.err or "Create failed")

    # Join Room
    with cB:
        room = st.text_input("Enter Room ID to Join").strip()
        if st.button("Join Room") and room:
            res = post(f"/join/{urllib.parse.quote(room)}", player_name=name)
            if res:
                st.session_state.update(
                    game_id=room,
                    player_id=res.get("player_id"),
                    role=res.get("role")
                )
                st.session_state.game_started = False
                st.session_state.cam_ctx = None
                st.session_state.detected_move = None
                st.session_state.move_ts = 0
                st.session_state.move_sent = False
                snap = get_state(room)
                if snap:
                    set_players(snap.get("players", {}))
                    st.success(f"Joined Room `{room}` as **Player {st.session_state.role}**")
                else:
                    st.error(st.session_state.err or "Failed to get initial game state")
            else:
                st.error(st.session_state.err or "Join failed")

    if not st.session_state.game_id:
        st.info("Create or join a room to continue.")
        st.stop()

    st.success(
        f"Connected as **{st.session_state.player_name} "
        f"(Player {st.session_state.role})** | Room `{st.session_state.game_id}`"
    )
