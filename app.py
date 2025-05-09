import asyncio, urllib.parse, requests, streamlit as st, websockets, av
from streamlit_webrtc import webrtc_streamer, WebRtcMode, VideoProcessorBase
from gesture_utils import RPSMove, GestureStabilizer, _classify_from_landmarks

API = "https://web-production-7e17f.up.railway.app"
st.set_page_config("RPS Gesture Game","✊"); st.title("✊ Rock-Paper-Scissors Online")

for k in ("game_id","player_id","role","player_name","players"): st.session_state.setdefault(k,None)

def api_post(path, **kw):
    r=requests.post(f"{API}{path}", json=kw, timeout=15); r.raise_for_status(); return r.json()

tab_home, tab_game = st.tabs(["🏠 Lobby","🎮 Game"])

# ───── Lobby ────────────────────────────────────────────────────
with tab_home:
    name = st.text_input("Your name", key="nm")
    if name: st.session_state.player_name = name

    if not st.session_state.player_name:
        st.stop()

    c1,c2 = st.columns(2)
    with c1:
        if st.button("Create Room"):
            res = api_post("/create_game", player_name=name)
            st.session_state.update(res)
    with c2:
        room = st.text_input("Room ID")
        if st.button("Join Room") and room:
            jid = urllib.parse.quote(room.strip())
            res = api_post(f"/join/{jid}", player_name=name)
            st.session_state.update(res, game_id=room)

    if st.session_state.game_id:
        st.success(f"Connected as **{st.session_state.player_name} (Player {st.session_state.role})**\nRoom: `{st.session_state.game_id}`")

# ───── Game ─────────────────────────────────────────────────────
with tab_game:
    if not st.session_state.game_id: st.info("Create / join room dahulu."); st.stop()

    ws_uri = API.replace("https","wss",1) + f"/ws/{st.session_state.game_id}/{st.session_state.player_id}"
    st.caption(f"WS → {ws_uri}")

    async def ws_listener():
        async with websockets.connect(ws_uri,ping_interval=20) as ws:
            while True:
                data = await ws.recv()
                st.session_state.players = eval(data) if isinstance(data,str) else data
                st.experimental_rerun()

    if "ws_task" not in st.session_state:
        asyncio.create_task(ws_listener())

    # tampilkan status pemain
    st.subheader("Players")
    pls = st.session_state.get("players",{}).get("players",{})
    col1,col2 = st.columns(2)
    for role,col in zip(("A","B"),(col1,col2)):
        p = pls.get(role)
        if p and p["name"]:
            col.write(f"**{role} – {p['name']}**")
            col.write("✅ Ready" if p["ready"] else "⏳ Not ready")
        else:
            col.write(f"*(waiting for Player {role})*")

    # tombol ready
    if st.button("I'm Ready") and not pls.get(st.session_state.role,{}).get("ready"):
        api_post(f"/ready/{st.session_state.game_id}", player_id=st.session_state.player_id)

    # —— webcam & shoot ——
    class VP(VideoProcessorBase):
        def __init__(self):
            self.det = GestureStabilizer(); self.last = RPSMove.NONE
        def recv(self, frame):
            img = frame.to_ndarray(format="bgr24")
            move = _classify_from_landmarks(self.det.process(img)) if hasattr(self.det,'process') else RPSMove.NONE
            self.last = self.det.update(move)
            return av.VideoFrame.from_ndarray(img,format="bgr24")
    ctx = webrtc_streamer(key="rps", mode=WebRtcMode.SENDONLY, video_processor_factory=VP)
    cur = ctx.video_processor.last if ctx.video_processor else RPSMove.NONE
    st.write(f"Current gesture → **{cur.value.upper()}**")
