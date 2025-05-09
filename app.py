import json, threading, asyncio, urllib.parse, requests, av, websockets
import streamlit as st
from streamlit_webrtc import webrtc_streamer, WebRtcMode, VideoProcessorBase
from gesture_utils import RPSMove, GestureStabilizer, _classify_from_landmarks

API = "https://web-production-7e17f.up.railway.app"

# ───── Streamlit setup ─────────────────────────────────────────
st.set_page_config("RPS Gesture Game", "✊")
st.title("✊ Rock-Paper-Scissors Online")

# default session values
for k in ("game_id","player_id","role","player_name","players","ws_thread"):
    st.session_state.setdefault(k, None)

# helper POST
def api_post(path, **payload):
    url = f"{API}{path}"
    r = requests.post(url, json=payload, timeout=15)
    try:
        r.raise_for_status()
    except requests.RequestException as e:
        st.error(f"⚠️  Backend error: {e}"); st.stop()
    return r.json()

# ───── Tabs ────────────────────────────────────────────────────
tab_lobby, tab_game = st.tabs(["🏠 Lobby", "🎮 Game"])

# -----------------------------------------------------------------
# LOBBY
# -----------------------------------------------------------------
with tab_lobby:
    name = st.text_input("Your name", key="user_name", max_chars=20)
    if name:
        st.session_state.player_name = name
    if not st.session_state.player_name:
        st.stop()

    col_create, col_join = st.columns(2)

    # Create room
    with col_create:
        if st.button("Create Room", key="btn_create"):

            res = api_post("/create_game",
                           player_name=st.session_state.player_name)
            # res = {game_id, player_id, role: 'A'}
            st.session_state.update(res)

    # Join room
    with col_join:
        join_id = st.text_input("Room ID to join", key="join_room")
        if st.button("Join Room", key="btn_join") and join_id:
            res = api_post(f"/join/{urllib.parse.quote(join_id.strip())}",
                           player_name=st.session_state.player_name)
            # res = {player_id, role: 'B'}
            st.session_state.update(res, game_id=join_id)

    if st.session_state.game_id:
        st.success(f"Connected as **{st.session_state.player_name} "
                   f"(Player {st.session_state.role})**  |  "
                   f"Room: `{st.session_state.game_id}`")

# -----------------------------------------------------------------
# GAME
# -----------------------------------------------------------------
with tab_game:
    if not st.session_state.game_id:
        st.info("Create or join a room first in *Lobby*"); st.stop()

    WS_URI = API.replace("https", "wss", 1) + \
             f"/ws/{st.session_state.game_id}/{st.session_state.player_id}"
    st.caption(f"WebSocket → {WS_URI}")

    # -------- WebSocket listener (background thread) -------------
    async def ws_listener():
        async with websockets.connect(WS_URI, ping_interval=20) as ws:
            while True:
                data = json.loads(await ws.recv())
                # {'players': {'A': {...}, 'B': {...}}}
                st.session_state.players = data["players"]
                st.experimental_rerun()

    def ensure_ws():
        if st.session_state.ws_thread:         # already running
            return
        threading.Thread(target=lambda: asyncio.run(ws_listener()),
                         daemon=True).start()
        st.session_state.ws_thread = True
    ensure_ws()

    # -------- tampilkan status pemain -----------------------------
    st.subheader("Players")
    players = (st.session_state.get("players") or {})  # safe dict
    colA, colB = st.columns(2)
    for role, col in zip(("A","B"), (colA,colB)):
        p = players.get(role)
        if p and p.get("name"):
            col.markdown(f"**{role} – {p['name']}**")
            col.write("✅ Ready" if p.get("ready") else "⏳ Not ready")
        else:
            col.write(f"*waiting Player {role}*")

    # -------- tombol Ready ---------------------------------------
    me_ready = players.get(st.session_state.role, {}).get("ready")
    if not me_ready:
        if st.button("I'm Ready",
                     key=f"ready_{st.session_state.player_id}"):
            api_post(f"/ready/{st.session_state.game_id}",
                     player_id=st.session_state.player_id)

    # -------- webcam & gesture -----------------------------------
    class VP(VideoProcessorBase):
        def __init__(self):
            self.stab = GestureStabilizer()
            self.last_move = RPSMove.NONE

        def recv(self, frame):
            img = frame.to_ndarray(format="bgr24")
            move = RPSMove.NONE
            # (GestureStabilizer.process tidak ada → gunakan mediapipe di luar)
            # Anda bisa tambahkan deteksi di sini jika perlu
            self.last_move = self.stab.update(move)
            return av.VideoFrame.from_ndarray(img, format="bgr24")

    ctx = webrtc_streamer(key="webrtc",
                          mode=WebRtcMode.SENDONLY,
                          video_processor_factory=VP)
    cur = ctx.video_processor.last_move if ctx.video_processor else RPSMove.NONE
    st.write(f"Current gesture → **{cur.value.upper()}**")
