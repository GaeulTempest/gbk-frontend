# ----------------- app.py -----------------
"""Streamlit front‑end with async WebSocket client & non‑blocking countdown.
Run:  streamlit run app.py  (requires streamlit>=1.30, websockets)
Env:  export API_URL="http://localhost:8000"
"""

import asyncio
import json
import os
import uuid

import streamlit as st
import websockets
from gesture_utils import RPSMove, GestureStabilizer, _classify_from_landmarks
import av
from streamlit_webrtc import VideoProcessorBase, webrtc_streamer, WebRtcMode
import mediapipe as mp

API_URL = os.getenv("API_URL", "http://localhost:8000")

st.set_page_config(page_title="RPS Gesture Game", page_icon="✊")
st.title("✊ Rock‑Paper‑Scissors Online (Gesture)")

# ------------- session state helpers -------------

def init_session():
    if "player_id" not in st.session_state:
        st.session_state.update({
            "game_id": None,
            "player_id": None,
            "role": None,
            "result": None,
        })

init_session()

# ------------- helper HTTP wrappers -------------
import requests

def api_post(path, **kwargs):
    return requests.post(f"{API_URL}{path}", json=kwargs).json()

def api_get(path):
    return requests.get(f"{API_URL}{path}").json()

# ------------- UI Tabs -------------
standby_tab, game_tab = st.tabs(["🔗 Standby", "🎮 Game"])

with standby_tab:
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Create New Room"):
            payload = api_post("/create_game")
            st.session_state.game_id = payload["game_id"]
            st.session_state.player_id = payload["player_id"]
            st.session_state.role = "HOST"
    with col2:
        join_id = st.text_input("Room ID", placeholder="paste room‑id here")
        if st.button("Join Room") and join_id:
            payload = api_post(f"/join/{join_id}")
            st.session_state.game_id = join_id
            st.session_state.player_id = payload["player_id"]
            st.session_state.role = "GUEST"

    if st.session_state.game_id:
        st.success(f"Connected as {st.session_state.role}. Share Room ID: {st.session_state.game_id}")

with game_tab:
    if not st.session_state.game_id:
        st.info("Create or join a room first.")
        st.stop()

    # async websocket connection inside Streamlit coroutine
    async def websocket_listener(queue):
        uri = f"{API_URL.replace('http', 'ws')}/ws/{st.session_state.game_id}/{st.session_state.player_id}"
        async with websockets.connect(uri, ping_interval=None) as ws:
            while True:
                try:
                    msg = await ws.recv()
                    await queue.put(json.loads(msg))
                except websockets.ConnectionClosed:
                    break

    queue: "asyncio.Queue" = asyncio.Queue()
    if "ws_task" not in st.session_state:
        st.session_state.ws_task = asyncio.create_task(websocket_listener(queue))

    status_placeholder = st.empty()

    # ---------- WebRTC video ----------

    class VideoProcessor(VideoProcessorBase):
        def __init__(self):
            self.hands = mp.solutions.hands.Hands(static_image_mode=False, max_num_hands=1)
            self.stab = GestureStabilizer()
            self.last_move = RPSMove.NONE

        def recv(self, frame: av.VideoFrame):
            img = frame.to_ndarray(format="bgr24")
            results = self.hands.process(img[:, :, ::-1])
            move = RPSMove.NONE
            if results.multi_hand_landmarks:
                move = _classify_from_landmarks(results.multi_hand_landmarks[0])
            self.last_move = self.stab.update(move)
            return av.VideoFrame.from_ndarray(img, format="bgr24")

    ctx = webrtc_streamer(key="gesture", mode=WebRtcMode.SENDONLY, video_processor_factory=VideoProcessor)

    if ctx.video_processor:
        move_detected = ctx.video_processor.last_move
    else:
        move_detected = RPSMove.NONE

    st.write(f"Current gesture: **{move_detected.value.upper()}**")

    # ----------- non‑blocking countdown & submit -------------
    countdown = st.empty()
    submit_btn = st.button("Shoot!")

    async def auto_countdown_and_submit():
        for i in range(3, 0, -1):
            countdown.markdown(f"### Prepare... {i}")
            await asyncio.sleep(1)
        countdown.markdown("### Go!")
        api_post(f"/move_ws/{st.session_state.game_id}", player_id=st.session_state.player_id, move=move_detected.value)

    if submit_btn:
        asyncio.create_task(auto_countdown_and_submit())

    # ----- listen queue for result -----
    async def display_result():
        while True:
            state = await queue.get()
            if state.get("winner"):
                if state["winner"] == "draw":
                    st.balloons()
                    st.success("It's a draw!")
                elif state["winner"] == st.session_state.player_id:
                    st.balloons()
                    st.success("You win!")
                else:
                    st.error("You lose!")
                break

    if "listener_task" not in st.session_state:
        st.session_state.listener_task = asyncio.create_task(display_result())

# ----------- Run backend (optional helper) -----------
# if __name__ == "__main__":
#     import uvicorn
#     uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)
# -----------------------------------------------------
