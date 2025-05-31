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
        def ws_loop():
            async def run():
                while True:
                    try:
                        async with websockets.connect(WS_URI, ping_interval=WS_PING) as ws:
                            while True:
                                data = json.loads(await ws.recv())
                                set_players(data["players"])
                    except: await asyncio.sleep(1)
            asyncio.run(run())
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
            post(f"/ready/{gid}", player_id=st.session_state.player_id)
            # Menambahkan status siap ke player yang menekan tombol
            st.session_state.players[st.session_state.role]["ready"] = True
            st.experimental_rerun()  # refresh halaman setelah status ready diperbarui
            
        if st.button("▶ Start Game", disabled=not both_ready, type="primary"):
            st.session_state.game_started = True
            st.session_state.camera_active = False
            st.session_state.force_camera_key += 1
            time.sleep(0.3)
            st.rerun()
        
        return st.stop()

    # Camera and Gameplay View
    st.header("Gameplay - Show Your Move!")
    
    # Camera Container System
    main_cam_container = st.empty()
    fallback_container = st.empty()
    
    if not st.session_state.camera_active:
        with main_cam_container:
            st.write("Initializing camera...")
            st.session_state.camera_active = True
            st.rerun()
    else:
        with main_cam_container:
            class VideoProcessor(VideoProcessorBase):
                def __init__(self):
                    self.last = RPSMove.NONE
                    self.last_frame = None
                
                def recv(self, frame):
                    try:
                        img = frame.to_ndarray(format="bgr24")
                        res = st.session_state.hands.process(img[:, :, ::-1])
                        
                        if res.multi_hand_landmarks:
                            mv = _classify_from_landmarks(res.multi_hand_landmarks[0])
                            stabilized = st.session_state.gesture_stabilizer.update(mv)
                            self.last = stabilized
                        else:
                            self.last = RPSMove.NONE
                            
                        self.last_frame = img
                    except Exception as e:
                        st.error(f"Camera error: {str(e)}")
                    return av.VideoFrame.from_ndarray(img, format="bgr24")

            ctx = webrtc_streamer(
                key=f"rps-cam-{st.session_state.force_camera_key}",
                mode=WebRtcMode.SENDONLY,
                video_processor_factory=VideoProcessor,
                async_processing=True,
                media_stream_constraints={"video": True, "audio": False},
                sendback_audio=False,
                rtc_configuration={"iceServers": []}
            )
            
            if ctx and ctx.state.playing:
                st.session_state.camera_ctx = ctx
                fallback_container.empty()
            else:
                fallback_container.warning("Please allow camera access...")

    # Gesture Detection Logic
    if st.session_state.camera_ctx and st.session_state.camera_ctx.video_processor:
        gesture = st.session_state.camera_ctx.video_processor.last
        st.session_state.detected_move = gesture
        
        st.subheader(f"Detected Move: **{gesture.value.upper()}**")
        
        # Auto-Submit Logic
        now = time.time()
        if gesture != RPSMove.NONE:
            if st.session_state.move_ts == 0:
                st.session_state.move_ts = now
                st.balloons()
            
            countdown = AUTO_SUBMIT_DELAY - (now - st.session_state.move_ts)
            if countdown > 0:
                st.progress(1 - (countdown / AUTO_SUBMIT_DELAY))
                st.caption(f"Submitting {gesture.value} in {int(countdown)}s...")
            else:
                post(f"/move/{gid}", 
                    player_id=st.session_state.player_id,
                    move=gesture.value)
                st.session_state.move_ts = 0
                st.success("Move submitted!")
        else:
            st.session_state.move_ts = 0

if __name__ == "__main__":
    main_game_view()
