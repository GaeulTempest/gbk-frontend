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
        response.raise_for_status()
        return response.json()
    except Exception as e:
        st.session_state.err = f"Failed to get STUN/TURN config: {str(e)}"
        return None

# ── Ambil konfigurasi STUN/TURN dari server ─────────────────
stun_turn_config = get_stun_turn_config()

if stun_turn_config:
    ice_servers = stun_turn_config.get("iceServers", [])
    RTC_CONFIG = RTCConfiguration({
        "iceServers": ice_servers
    })
else:
    st.warning("STUN/TURN configuration could not be retrieved.")

# =========================================================
#  LOBBY SECTION
# =========================================================
tab_lobby, tab_player, tab_game = st.tabs(["🏠 Lobby", "👾 Player", "🎮 Game"])

# ... (bagian kode lainnya tetap sama) ...

# =========================================================
#  GAME SECTION
# =========================================================
with tab_game:
    if not st.session_state.game_started:
        st.warning("The game will start once both players are ready.")
        st.stop()

    # Menampilkan perangkat kamera menggunakan webrtc_streamer
    st.write("### Pilih Perangkat Kamera")
    
    # Penggunaan webrtc_streamer dengan RTC_CONFIG yang sudah diatur
    if stun_turn_config:
        st.session_state.cam_ctx = webrtc_streamer(
            key="cam",
            mode=WebRtcMode.SENDONLY,
            video_processor_factory=VideoProcessorBase,
            async_processing=True,
            rtc_configuration=RTC_CONFIG
        )
    
    st.info("Tekan **Start Game** untuk memulai permainan!")
