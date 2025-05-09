import json, threading, asyncio, urllib.parse, requests, av, websockets
import streamlit as st
from streamlit_webrtc import webrtc_streamer, WebRtcMode, VideoProcessorBase
from gesture_utils import RPSMove, GestureStabilizer

API = "https://web-production-7e17f.up.railway.app"

# ── Streamlit config ─────────────────────────────────────
st.set_page_config("RPS Gesture Game", "✊")
st.title("✊ Rock-Paper-Scissors Online")

for k in ("game_id","player_id","role","player_name","players","ws_thread"):
    st.session_state.setdefault(k, None)

def api_post(path, **payload):
    r = requests.post(f"{API}{path}", json=payload, timeout=15)
    try: r.raise_for_status()
    except requests.HTTPError as e:
        st.error(f"Backend says: {e.response.text}"); st.stop()
    return r.json()

# ── tabs ─────────────────────────────────────────────────
tab_lobby, tab_game = st.tabs(["🏠 Lobby", "🎮 Game"])

# -------- LOBBY --------
with tab_lobby:
    name = st.text_input("Your name", key="nm", max_chars=20).strip()
    if name: st.session_state.player_name = name
    if not st.session_state.player_name: st.stop()

    c_create, c_join = st.columns(2)

    # create
    with c_create:
        if st.button("Create Room", key="btn_create"):
            res = api_post("/create_game", player_name=name)
            st.session_state.update(res)

    # join
    with c_join:
        room_id = st.text_input("Room ID", key="room_join")
        if st.button("Join Room", key="btn_join") and room_id:
            res = api_post(f"/join/{urllib.parse.quote(room_id.strip())}",
                           player_name=name)
            st.session_state.update(res, game_id=room_id)

    if st.session_state.game_id:
        st.success(
            f"Connected as **{st.session_state.player_name} "
            f"(Player {st.session_state.role})**  |  "
            f"Room: `{st.session_state.game_id}`"
        )

# -------- GAME --------
with tab_game:
    if not st.session_state.game_id:
        st.info("Create or join a room first."); st.stop()

    WS_URI = API.replace("https","wss",1) + \
             f"/ws/{st.session_state.game_id}/{st.session_state.player_id}"
    st.caption(f"WS → {WS_URI}")

    # background WS listener
    async def ws_listener():
        async with websockets.connect(WS_URI, ping_interval=20) as ws:
            while True:
                data = json.loads(await ws.recv())
                st.session_state.players = data["players"]
                st.experimental_rerun()

    if not st.session_state.ws_thread:
        threading.Thread(target=lambda: asyncio.run(ws_listener()),
                         daemon=True).start()
        st.session_state.ws_thread = True

    # players status
    players = st.session_state.get("players") or {}
    cA, cB = st.columns(2)
    for role, col in zip(("A","B"), (cA,cB)):
        p = players.get(role)
        if p and p.get("name"):
            col.markdown(f"**{role} – {p['name']}**")
            col.write("✅ Ready" if p.get("ready") else "⏳ Not ready")
        else:
            col.write(f"*waiting Player {role}*")

    # ready button
    my_ready = players.get(st.session_state.role, {}).get("ready")
    if not my_ready and st.button("I'm Ready",
                                  key=f"ready_{st.session_state.player_id}"):
        api_post(f"/ready/{st.session_state.game_id}",
                 player_id=st.session_state.player_id)

    # webcam & gesture (dummy example)
    class VP(VideoProcessorBase):
        def __init__(self):
            self.stab = GestureStabilizer(); self.last = RPSMove.NONE
        def recv(self, f):
            img = f.to_ndarray(format="bgr24")
            self.last = self.stab.update(RPSMove.NONE)
            return av.VideoFrame.from_ndarray(img,format="bgr24")

    ctx = webrtc_streamer(key="wc", mode=WebRtcMode.SENDONLY,
                          video_processor_factory=VP)
    cur = ctx.video_processor.last if ctx.video_processor else RPSMove.NONE
    st.write(f"Current gesture → **{cur.value.upper()}**")
