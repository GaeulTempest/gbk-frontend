import json, threading, asyncio, urllib.parse, requests, av, websockets
import streamlit as st
from streamlit_webrtc import webrtc_streamer, WebRtcMode, VideoProcessorBase
from gesture_utils import RPSMove, GestureStabilizer, _classify_from_landmarks

API = "https://web-production-7e17f.up.railway.app"

st.set_page_config("RPS Gesture Game", "✊")
st.title("✊ Rock-Paper-Scissors Online")

# default state
for k in ("game_id","player_id","role","player_name","players","ws_thread"):
    st.session_state.setdefault(k, None)

def api_post(path, **d):
    r = requests.post(f"{API}{path}", json=d, timeout=15); r.raise_for_status(); return r.json()

# ───── Lobby ───────────────────────────────
tab_home, tab_game = st.tabs(["🏠 Lobby", "🎮 Game"])
with tab_home:
    name = st.text_input("Your name", key="nm", max_chars=20)
    if name: st.session_state.player_name = name
    if not st.session_state.player_name: st.stop()

    colA, colB = st.columns(2)
    with colA:
        if st.button("Create Room", key="btn_create"):
            res = api_post("/create_game", player_name=name)
            st.session_state.update(res)     # game_id, player_id, role
    with colB:
        room = st.text_input("Room ID")
        if st.button("Join Room", key="btn_join") and room:
            res = api_post(f"/join/{urllib.parse.quote(room)}",
                           player_name=name)
            st.session_state.update(res, game_id=room)

    if st.session_state.game_id:
        st.success(f"Connected as **{st.session_state.player_name} "
                   f"(Player {st.session_state.role})**  |  "
                   f"Room `{st.session_state.game_id}`")

# ───── Game ────────────────────────────────
with tab_game:
    if not st.session_state.game_id:
        st.info("Create / join room dahulu."); st.stop()

    WS_URI = API.replace("https", "wss", 1) + \
             f"/ws/{st.session_state.game_id}/{st.session_state.player_id}"
    st.caption(f"WS → {WS_URI}")

    async def _ws_listener():
        async with websockets.connect(WS_URI, ping_interval=20) as ws:
            while True:
                data = json.loads(await ws.recv())
                st.session_state.players = data["players"]
                st.experimental_rerun()

    def _ensure_ws():
        if st.session_state.ws_thread: return
        threading.Thread(target=lambda: asyncio.run(_ws_listener()),
                         daemon=True).start()
        st.session_state.ws_thread = True
    _ensure_ws()

    # status pemain
    pls = st.session_state.get("players") or {}
    col1, col2 = st.columns(2)
    for role, col in zip(("A","B"), (col1,col2)):
        p = pls.get(role)
        if p and p.get("name"):
            col.markdown(f"**{role} – {p['name']}**")
            col.write("✅ Ready" if p.get("ready") else "⏳ Not ready")
        else:
            col.write(f"*waiting Player {role}*")

    # tombol ready
    me_ready = pls.get(st.session_state.role, {}).get("ready")
    if not me_ready and st.button("I'm Ready", key=f"ready_{st.session_state.player_id}"):
        api_post(f"/ready/{st.session_state.game_id}",
                 player_id=st.session_state.player_id)

    # webcam + gesture
    class VP(VideoProcessorBase):
        def __init__(self):
            self.det = GestureStabilizer(); self.last = RPSMove.NONE
        def recv(self, frame):
            img = frame.to_ndarray(format="bgr24")
            move = _classify_from_landmarks(self.det.process(img)) \
                   if hasattr(self.det,'process') else RPSMove.NONE
            self.last = self.det.update(move)
            return av.VideoFrame.from_ndarray(img, format="bgr24")

    ctx = webrtc_streamer(key="cam",
                          mode=WebRtcMode.SENDONLY,
                          video_processor_factory=VP)
    gesture = ctx.video_processor.last if ctx.video_processor else RPSMove.NONE
    st.write(f"Current gesture → **{gesture.value.upper()}**")
