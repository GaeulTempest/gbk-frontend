# ----------------- app.py -----------------
"""Streamlit front‑end (gesture + WebSocket) siap konek ke backend Railway."""

import os, asyncio, json, requests, av, mediapipe as mp, streamlit as st
import websockets
from streamlit_webrtc import webrtc_streamer, WebRtcMode, VideoProcessorBase
from gesture_utils import RPSMove, GestureStabilizer, _classify_from_landmarks

# ---------- Konfigurasi URL backend ----------
API_URL = (
    st.secrets.get("API_URL")              # via secrets.toml jika ada
    or os.getenv("API_URL")                # via environment variable
    or "https://web-production-7e17f.up.railway.app"   # fallback default
)

st.set_page_config("RPS Gesture Game", "✊")
st.title("✊ Rock‑Paper‑Scissors Online")

# ---------- State ----------
for k in ("game_id", "player_id", "role"):
    st.session_state.setdefault(k, None)

# ---------- Helper HTTP ----------
def api_post(path, **kw):
    url = f"{API_URL}{path}"
    try:
        resp = requests.post(url, json=kw, timeout=15)
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.RequestException as e:
        st.error(f"⚠️ Gagal menghubungi backend:\n`{url}`\n\n{e}")
        st.stop()

# ---------- Tabs ----------
tab_standby, tab_game = st.tabs(["🔗 Standby", "🎮 Game"])

with tab_standby:
    c1, c2 = st.columns(2)
    with c1:
        if st.button("Create Room"):
            res = api_post("/create_game")
            st.session_state.update(res, role="HOST")
    with c2:
        join_id = st.text_input("Room ID")
        if st.button("Join Room") and join_id:
            res = api_post(f"/join/{join_id}")
            st.session_state.update(game_id=join_id,
                                    player_id=res["player_id"],
                                    role="GUEST")
    if st.session_state.game_id:
        st.success(f"Connected as **{st.session_state.role}** | Room: `{st.session_state.game_id}`")

with tab_game:
    if not st.session_state.game_id:
        st.info("Buat/join room dulu di tab Standby.")
        st.stop()

    # ---------- WebSocket listener ----------
    ws_uri = API_URL.replace("https", "wss", 1).replace("http", "ws", 1) + \
             f"/ws/{st.session_state.game_id}/{st.session_state.player_id}"

    queue: "asyncio.Queue" = asyncio.Queue()

    async def listener():
        async with websockets.connect(ws_uri, ping_interval=20, ping_timeout=10) as ws:
            while True:
                try:
                    await queue.put(json.loads(await ws.recv()))
                except websockets.ConnectionClosed:
                    break

    if "ws_task" not in st.session_state:
        st.session_state.ws_task = asyncio.create_task(listener())

    # ---------- Webcam gesture ----------
    class VP(VideoProcessorBase):
        def __init__(self):
            self.detector = mp.solutions.hands.Hands(max_num_hands=1)
            self.stab = GestureStabilizer()
            self.last_move = RPSMove.NONE
        def recv(self, frame):
            img = frame.to_ndarray(format="bgr24")
            res = self.detector.process(img[:, :, ::-1])
            move = RPSMove.NONE
            if res.multi_hand_landmarks:
                move = _classify_from_landmarks(res.multi_hand_landmarks[0])
            self.last_move = self.stab.update(move)
            return av.VideoFrame.from_ndarray(img, format="bgr24")

    ctx = webrtc_streamer(key="rps", mode=WebRtcMode.SENDONLY,
                          video_processor_factory=VP)
    current_move = ctx.video_processor.last_move if ctx.video_processor else RPSMove.NONE
    st.write(f"Current gesture → **{current_move.value.upper()}**")

    # ---------- Countdown & submit ----------
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

    # ---------- Tampilkan hasil ----------
    async def show_result():
        while True:
            state = await queue.get()
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
