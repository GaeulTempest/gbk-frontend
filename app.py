import urllib.parse
import streamlit as st
import requests
import asyncio
import websockets
from streamlit_webrtc import webrtc_streamer, WebRtcMode, VideoProcessorBase
from gesture_utils import RPSMove, GestureStabilizer, _classify_from_landmarks

# API URL for backend (ensure the correct URL is set here)
API_URL = "https://web-production-7e17f.up.railway.app"

# Streamlit page configuration
st.set_page_config("RPS Gesture Game", "✊")
st.title("✊ Rock‑Paper‑Scissors Online")

# Session state for game details
for k in ("game_id", "player_id", "role", "player_name"):
    st.session_state.setdefault(k, None)

# Helper HTTP function to post requests to backend
def api_post(path, **kw):
    url = f"{API_URL}{path}"
    try:
        resp = requests.post(url, json=kw, timeout=15)
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.RequestException as e:
        st.error(f"⚠️ Failed to contact backend: `{url}`\n\n{e}")
        st.stop()

# Tabs for UI
tab_standby, tab_game = st.tabs(["🔗 Standby", "🎮 Game"])

# Standby tab for creating or joining a room
with tab_standby:
    # Input nama pemain
    player_name = st.text_input("Enter your name", max_chars=20)
    if player_name:
        st.session_state.player_name = player_name  # Simpan nama pemain di session_state

    # Pastikan nama pemain telah diisi sebelum membuat atau bergabung dengan room
    if st.session_state.player_name is None or st.session_state.player_name == "":
        st.warning("Please enter your name before creating or joining a room.")

    c1, c2 = st.columns(2)
    with c1:
        if st.button("Create Room") and st.session_state.player_name:
            res = api_post("/create_game", player_name=st.session_state.player_name)  # Kirim nama pemain ke backend
            st.session_state.update(res, role="HOST")
            st.session_state.game_id = res["game_id"]
    with c2:
        join_id = st.text_input("Room ID")
        if st.button("Join Room") and join_id and st.session_state.player_name:
            encoded_id = urllib.parse.quote(join_id.strip())  # Encoding ID untuk memastikan URL valid
            res = api_post(f"/join/{encoded_id}", player_name=st.session_state.player_name)  # Kirim nama pemain ke backend
            st.session_state.update(game_id=join_id,
                                    player_id=res["player_id"],
                                    role="GUEST")

    if st.session_state.game_id:
        st.success(f"Connected as **{st.session_state.role}** | Room: `{st.session_state.game_id}`")

# Game tab for displaying and interacting with the game
with tab_game:
    if not st.session_state.game_id:
        st.info("Please create or join a room in the Standby tab.")
        st.stop()

    # WebSocket connection setup
    ws_uri = API_URL.replace("https", "wss", 1).replace("http", "ws", 1) + \
             f"/ws/{st.session_state.game_id}/{st.session_state.player_id}"

    # Log the WebSocket URL for debugging purposes
    st.write(f"WebSocket URL: {ws_uri}")

    # Listener function to handle WebSocket communication
    async def listener():
        try:
            async with websockets.connect(ws_uri, ping_interval=20, ping_timeout=10) as ws:
                while True:
                    try:
                        message = await ws.recv()
                        st.session_state.game_state = message  # Update game state with message
                        st.experimental_rerun()  # Trigger a rerun of the app
                    except websockets.ConnectionClosed:
                        st.warning("WebSocket connection closed.")
                        break
        except websockets.exceptions.InvalidStatus as e:
            st.error(f"WebSocket Error: {e}")
            st.stop()
        except Exception as e:
            st.error(f"Unexpected Error: {e}")
            st.stop()

    # Ensure the WebSocket listener runs only once
    if "ws_task" not in st.session_state:
        asyncio.run(listener())

    # Display the current gesture and waiting for a player to shoot
    class VP(VideoProcessorBase):
        def __init__(self):
            self.detector = GestureStabilizer()
            self.last_move = RPSMove.NONE

        def recv(self, frame):
            img = frame.to_ndarray(format="bgr24")
            res = self.detector.process(img)
            move = RPSMove.NONE
            if res:
                move = _classify_from_landmarks(res)
            self.last_move = self.detector.update(move)
            return av.VideoFrame.from_ndarray(img, format="bgr24")

    # WebRTC stream setup for gesture recognition
    ctx = webrtc_streamer(key="rps", mode=WebRtcMode.SENDONLY,
                          video_processor_factory=VP)
    current_move = ctx.video_processor.last_move if ctx.video_processor else RPSMove.NONE
    st.write(f"Current gesture → **{current_move.value.upper()}**")  # Fixing the f-string

    # Countdown and submit move button
    placeholder = st.empty()
    if st.button("Shoot!"):
        async def shoot():
            for i in range(3, 0, -1):
                placeholder.markdown(f"### Prepare… {i}")
                await asyncio.sleep(1)
            placeholder.markdown("### Go!")
            api_post(f"/move_ws/{st.session_state.game_id}",
                     player_id=st.session_state.player_id,
                     move=current_move.value)

        asyncio.create_task(shoot())

    # Handle game results
    async def show_result():
        while True:
            state = await ws.recv()
            if state.get("winner"):
                if state["winner"] == "draw":
                    st.balloons(); st.success("Draw!")
                elif state["winner"] == st.session_state.player_id:
                    st.balloons(); st.success("You WIN! 🏆")
                else:
                    st.error("You lose 😢")
                break

    if "result_task" not in st.session_state:
        st.session_state.result_task = asyncio.create_task(show_result())
