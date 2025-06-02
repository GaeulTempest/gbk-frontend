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

def _h(pl): 
    return json.dumps(pl, sort_keys=True)

def set_players(pl):
    """Update hanya di fase LOBBY."""
    if st.session_state.game_started:
        return
    h = _h(pl)
    if h != st.session_state._hash:
        st.session_state.players = pl
        st.session_state._hash = h

# =========================================================
#  LOBBY SECTION (Kembali ke semula)
# =========================================================
tab_lobby, tab_player, tab_game = st.tabs(["🏠 Lobby", "👾 Player", "🎮 Game"])

with tab_lobby:
    name = st.text_input("Your name", max_chars=20).strip()
    if name:
        st.session_state.player_name = name

    if not st.session_state.player_name:
        st.warning("Enter your name to continue.")
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
            else:
                st.error(st.session_state.err or "Create failed")

    # Join Room
    with cB:
        room = st.text_input("Room ID").strip()
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
                if
