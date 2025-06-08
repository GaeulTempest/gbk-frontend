import json, threading, asyncio, time, urllib.parse, requests, av, websockets, mediapipe as mp
import streamlit as st
from streamlit_webrtc import webrtc_streamer, WebRtcMode, RTCConfiguration, VideoProcessorBase
from gesture_utils import RPSMove, GestureStabilizer, _classify_from_landmarks
import base64  # Add this import statement for base64 encoding

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
        ident = "wawanshot"
        secret = "6ebc02ec-4257-11f0-9543-aa614b70fb40"
        channel = "multiplayergbk"
        
        # Encode the credentials to Base64 for Basic Authentication
        auth_value = f"{ident}:{secret}"
        base64_auth_value = base64.b64encode(auth_value.encode('utf-8')).decode('utf-8')  # Fix here by importing base64

        # URL to get STUN/TURN servers from Xirsys
        url = f"https://global.xirsys.net/_turn/{channel}"

        # Headers for Xirsys API request
        headers = {
            "Authorization": f"Basic {base64_auth_value}",
            "Content-Type": "application/json"
        }

        # Data for Xirsys API request
        data = {"format": "urls"}

        # Make the PUT request to Xirsys
        response = requests.put(url, headers=headers, json=data)
        response.raise_for_status()

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
        try:
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
        except requests.RequestException as e:
            st.error(f"Failed to join room: {str(e)}")

    if not st.session_state.game_id:
        st.info("Create or join a room to continue.")
        st.stop()

    st.success(
        f"Connected as **{st.session_state.player_name} "
        f"(Player {st.session_state.role})** | Room `{st.session_state.game_id}`"
    )

# =========================================================
#  GAME TAB
# =========================================================
with tab_game:
    gid = st.session_state.game_id
    if not gid:
        st.info("Go to Lobby to create or join a room.")
        st.stop()

    if not st.session_state.game_started:
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
                        except:
                            await asyncio.sleep(1)
                asyncio.run(run())
            threading.Thread(target=ws_loop, daemon=True).start()
            st.session_state.ws_thread = True

        if st.button("🔄 Refresh status"):
            snap = get_state(gid)
            if snap:
                set_players(snap["players"])
            else:
                st.error(st.session_state.err or "Fetch state failed")

        pl = st.session_state.players
        c1, c2 = st.columns(2)
        for role, col in zip(("A", "B"), (c1, c2)):
            p = pl.get(role, {})
            if p.get("name"):
                col.markdown(f"**{role} – {p['name']}**")
                col.write("✅ Ready" if p.get("ready") else "⏳ Not ready")
            else:
                col.write(f"*waiting Player {role}*")

        me_ready = pl.get(st.session_state.role, {}).get("ready", False)
        both_ready = pl.get("A", {}).get("ready") and pl.get("B", {}).get("ready")

        if not me_ready:
            if st.button("I'm Ready", key=f"ready_{st.session_state.player_id}"):

                snap = post(f"/ready/{gid}", player_id=st.session_state.player_id)
                if snap:
                    set_players(snap["players"])
                else:
                    st.error(st.session_state.err or "Ready failed")

        if st.button("▶️ Start Game", disabled=not both_ready):
            st.session_state.game_started = True

        st.info("Press Ready on both sides, then click **Start Game**")
        st.stop()

    if st.session_state.cam_ctx is None:
        class VP(VideoProcessorBase):
            def __init__(self):
                self.hands = mp.solutions.hands.Hands(max_num_hands=1)
                self.stab = GestureStabilizer()
                self.last = RPSMove.NONE

            def recv(self, frame):
                img = frame.to_ndarray(format="bgr24")
                res = self.hands.process(img[:, :, ::-1])
                mv = (_classify_from_landmarks(res.multi_hand_landmarks[0])
                      if res and res.multi_hand_landmarks else RPSMove.NONE)
                self.last = self.stab.update(mv)
                return av.VideoFrame.from_ndarray(img, format="bgr24")

        st.session_state.cam_ctx = webrtc_streamer(
            key="cam",
            mode=WebRtcMode.SENDONLY,
            video_processor_factory=VP,
            async_processing=True,
            rtc_configuration=RTC_CONFIG  # menggunakan konfigurasi STUN/TURN Xirsys
        )

    ctx = st.session_state.cam_ctx
    gesture = ctx.video_processor.last if ctx and ctx.video_processor else RPSMove.NONE
    st.write(f"Live gesture → **{gesture.value.upper()}**")

    now = time.time()
    if gesture == RPSMove.NONE:
        st.session_state.detected_move = None
        st.session_state.move_ts = now
        st.session_state.move_sent = False
    else:
        if st.session_state.detected_move != gesture:
            st.session_state.detected_move = gesture
            st.session_state.move_ts = now
            st.session_state.move_sent = False
        elif (not st.session_state.move_sent and
              now - st.session_state.move_ts >= AUTO_SUBMIT_DELAY):
            post(f"/move/{gid}",
                 player_id=st.session_state.player_id,
                 move=gesture.value)
            st.session_state.move_sent = True
            st.success(f"Sent **{gesture.value.upper()}**!")
