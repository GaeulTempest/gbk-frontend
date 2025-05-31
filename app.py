import json, threading, asyncio, time, urllib.parse, requests, av, websockets, mediapipe as mp
import streamlit as st
from streamlit_webrtc import webrtc_streamer, WebRtcMode, VideoProcessorBase
from gesture_utils import RPSMove, GestureStabilizer, _classify_from_landmarks
import logging  # Tambahkan import logging

# Konfigurasi logger
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("StreamlitApp")  # Inisialisasi logger

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
    if name: st.session_state.player_name = name
    
    if not st.session_state.player_name:
        st.warning("Enter your name to continue.")
        st.stop()

    # Create/Join Room
    room = st.text_input("Room ID").strip()
    c1, c2 = st.columns(2)
    with c1:
        if st.button("Create Room") and name:
            res = post("/create_game", player_name=name)
            if res: st.session_state.update(res)
    with c2:
        if st.button("Join Room") and room and name:
            res = post(f"/join/{room}", player_name=name)
            if 'error' in res:  # Cek jika error
                st.error("Room ID tidak ditemukan.")
            elif res:
                st.session_state.update(res)

# =========================================================
#  GAME TAB
# =========================================================
def main_game_view():
    gid = st.session_state.game_id
    if not gid: return st.info("Create or join a room first")

    # WebSocket Connection
    if not st.session_state.ws_thread:
        WS_URI = API.replace("https", "wss", 1) + f"/ws/{gid}/{st.session_state.player_id}"
        log.info(f"Connecting to WebSocket: {WS_URI}")  # Menambahkan log di sini
        def ws_loop():
            async def run():
                while True:
                    try:
                        async with websockets.connect(WS_URI, ping_interval=WS_PING) as ws:
                            log.info("WebSocket connected!")  # WebSocket berhasil terhubung
                            while True:
                                data = json.loads(await ws.recv())
                                set_players(data["players"])
                    except Exception as e:
                        log.error(f"Error connecting to WebSocket: {str(e)}")  # Error WebSocket
                        await asyncio.sleep(1)
        threading.Thread(target=ws_loop, daemon=True).start()
        st.session_state.ws_thread = True

    # Game Lobby State
    if not st.session_state.game_started:
        pl = st.session_state.players
        st.header("Game Lobby")
        st.write(f"Room ID: `{gid}`")
        
        # Player Status
        c1, c2 = st.columns(2)
        for role, col in zip(["A", "B"], [c1, c2]):
            p = pl.get(role, {})
            col.markdown(f"### Player {role}: {p.get('name', 'Waiting')}")  # Menampilkan nama pemain
            col.write("✅ Ready" if p.get('ready') else "⏳ Not ready")

        # Ready/Start Controls
        me_ready = pl.get(st.session_state.role, {}).get("ready", False)
        both_ready = all(pl.get(r, {}).get("ready") for r in ["A", "B"])
        
        if not me_ready and st.button("I'm Ready"):
            # Pastikan st.session_state.role valid dan ada dalam session_state
            if st.session_state.role in st.session_state.players:
                post(f"/ready/{gid}", player_id=st.session_state.player_id)
                #
