import json, threading, asyncio, urllib.parse, requests, av, websockets
import streamlit as st
from streamlit_webrtc import webrtc_streamer, WebRtcMode, VideoProcessorBase
from gesture_utils import RPSMove, GestureStabilizer, _classify_from_landmarks

API = "https://web-production-7e17f.up.railway.app"

# ───── Streamlit basic ───────────────────────────────────────────
st.set_page_config("RPS Gesture Game", "✊")
st.title("✊ Rock-Paper-Scissors Online")

# session defaults
for k in ("game_id","player_id","role","player_name","players","ws_thread"):
    st.session_state.setdefault(k, None)

# helper POST
def api_post(path, **data):
    try:
        r = requests.post(f"{API}{path}", json=data, timeout=15)
        r.raise_for_status(); return r.json()
    except requests.RequestException as e:
        st.error(f"⚠️ Backend error: {e}"); st.stop()

tab_home, tab_game = st.tabs(["🏠 Lobby","🎮 Game"])

# ───── LOBBY ─────────────────────────────────────────────────────
with tab_home:
    name = st.text_input("Your name", key="name", max_chars=20)
    if name: st.session_state.player_name = name

    if not st.session_state.player_name:
        st.stop()

    colA, colB = st.columns(2)
    with colA:
        if st.button("Create Room"):
            res = api_post("/create_game", player_name=name)
            st.session_state.update(res)          # game_id, player_id, role
    with colB:
        room = st.text_input("Room ID")
        if st.button("Join Room") and room:
            res = api_post(f"/join/{urllib.parse.quote(room)}",
                           player_name=name)
            st.session_state.update(res, game_id=room)

    if st.session_state.game_id:
        st.success(f"Connected as **{st.session_state.player_name} "
                   f"(Player {st.session_state.role})**  |  "
                   f"Room `{st.session_state.game_id}`")

# ───── GAME ──────────────────────────────────────────────────────
with tab_game:
    if not st.session_state.game_id:
        st.info("Create / join room terlebih dahulu di tab *Lobby*"); st.stop()

    # URL WebSocket
    WS_URI = API.replace("https","wss",1) + \
             f"/ws/{st.session_state.game_id}/{st.session_state.player_id}"
    st.caption(f"WebSocket → {WS_URI}")

    # ---------- jalankan listener di thread terpisah ----------
    async def ws_listener():
        async with websockets.connect(WS_URI, ping_interval=20) as ws:
            while True:
                data = json.loads(await ws.recv())
                st.session_state.players = data["players"]
                st.experimental_rerun()

    def ensure_ws_running():
        if st.session_state.ws_thread:           # sudah ada
            return
        def _run(): asyncio.run(ws_listener())
        threading.Thread(target=_run, daemon=True).start()
        st.session_state.ws_thread = True

    ensure_ws_running()

    # ---------- tampilan status pemain ----------
    st.subheader("Players")
    pls = st.session_state.get("players", {})
    col1, col2 = st.columns(2)
    for role, col in zip(("A","B"), (col1,col2)):
        p = pls.get(role)
        if p and p["name"]:
            col.markdown(f"**{role} – {p['name']}**")
            col.write("✅ Ready" if p["ready"] else "⏳ Not ready")
        else:
            col.write(f"*(waiting for Player {role})*")

    # tombol Ready
    if pls.get(st.session_state.role, {}).get("ready") is not True:
        if st.button("I'm Ready"):
            api_post(f"/ready/{st.session_state.game_id}",
                     player_id=st.session_state.player_id)

    # ---------- gesture webcam ----------
    class VP(VideoProcessorBase):
        def __init__(self):
            self.hands = GestureStabilizer(); self.last = RPSMove.NONE
        def recv(self, frame):
            img = frame.to_ndarray(format="bgr24")
            move = _classify_from_landmarks(self.hands.process(img)) \
                   if hasattr(self.hands,"process") else RPSMove.NONE
            self.last = self.hands.update(move)
            return av.VideoFrame.from_ndarray(img, format="bgr24")

    ctx = webrtc_streamer(key="cam", mode=WebRtcMode.SENDONLY,
                          video_processor_factory=VP)
    cur = ctx.video_processor.last if ctx.video_processor else RPSMove.NONE
    st.write(f"Current gesture → **{cur.value.upper()}**")
