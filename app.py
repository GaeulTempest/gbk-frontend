import json, threading, asyncio, urllib.parse, requests, av, websockets, mediapipe as mp
import streamlit as st
from streamlit_webrtc import webrtc_streamer, WebRtcMode, VideoProcessorBase
from gesture_utils import RPSMove, GestureStabilizer, _classify_from_landmarks

API = "https://web-production-7e17f.up.railway.app"

st.set_page_config("RPS Gesture Game", "✊")
st.title("✊ Rock-Paper-Scissors Online")

for k in ("game_id","player_id","role","player_name","players","ws_thread"):
    st.session_state.setdefault(k, None)

def api_post(path, **p):
    r = requests.post(f"{API}{path}", json=p, timeout=15)
    r.raise_for_status(); return r.json()

# ── LOBBY ────────────────────────────────────────────────
tab_lobby, tab_game = st.tabs(["🏠 Lobby","🎮 Game"])

with tab_lobby:
    name = st.text_input("Your name", max_chars=20).strip()
    if name: st.session_state.player_name = name
    if not st.session_state.player_name: st.stop()

    cA,cB = st.columns(2)
    with cA:
        if st.button("Create Room"):
            st.session_state.update(
                api_post("/create_game", player_name=name)
            )
    with cB:
        room = st.text_input("Room ID")
        if st.button("Join Room") and room:
            st.session_state.update(
                api_post(f"/join/{urllib.parse.quote(room.strip())}",
                         player_name=name),
                game_id=room
            )

    if st.session_state.game_id:
        st.success(f"Connected as **{st.session_state.player_name} "
                   f"(Player {st.session_state.role})** | "
                   f"Room `{st.session_state.game_id}`")

# ── GAME ─────────────────────────────────────────────────
with tab_game:
    if not st.session_state.game_id:
        st.info("Create or join room first."); st.stop()

    WS_URI = API.replace("https","wss",1)+f"/ws/{st.session_state.game_id}/{st.session_state.player_id}"
    st.caption(f"WS → {WS_URI}")

    # background WS listener (auto-reconnect)
    async def ws_loop():
        while True:
            try:
                async with websockets.connect(WS_URI, ping_interval=20) as ws:
                    while True:
                        data = json.loads(await ws.recv())
                        st.session_state.players = data["players"]
                        st.experimental_rerun()
            except: await asyncio.sleep(1)

    if not st.session_state.ws_thread:
        threading.Thread(target=lambda: asyncio.run(ws_loop()),
                         daemon=True).start()
        st.session_state.ws_thread = True

    # players display
    players = st.session_state.get("players") or {}
    colA,colB = st.columns(2)
    for role,col in zip(("A","B"),(colA,colB)):
        p = players.get(role)
        if p and p.get("name"):
            col.markdown(f"**{role} – {p['name']}**")
            col.write("✅ Ready" if p.get("ready") else "⏳ Not ready")
        else: col.write(f"*waiting Player {role}*")

    my_role  = st.session_state.role
    my_ready = players.get(my_role, {}).get("ready", False)
    both_ready = players.get("A",{}).get("ready") and players.get("B",{}).get("ready")

    # READY button (no experimental_rerun here)
    if not my_ready and st.button("I'm Ready", key=f"ready_{st.session_state.player_id}"):
        players.setdefault(my_role, {})["ready"] = True   # local optimistic
        st.session_state.players = players
        api_post(f"/ready/{st.session_state.game_id}",
                 player_id=st.session_state.player_id)

    if not both_ready:
        st.info("Waiting until **both players** press *I'm Ready*…")
        st.stop()

    st.success("Both players ready – game starts!")

    # webcam & live gesture
    class VP(VideoProcessorBase):
        def __init__(self):
            self.hands = mp.solutions.hands.Hands(max_num_hands=1)
            self.stab  = GestureStabilizer(); self.last = RPSMove.NONE
        def recv(self, frame):
            img = frame.to_ndarray(format="bgr24")
            res = self.hands.process(img[:,:,::-1])
            move = RPSMove.NONE
            if res.multi_hand_landmarks:
                move = _classify_from_landmarks(res.multi_hand_landmarks[0])
            self.last = self.stab.update(move)
            return av.VideoFrame.from_ndarray(img,format="bgr24")

    ctx = webrtc_streamer(key="wc", mode=WebRtcMode.SENDONLY,
                          video_processor_factory=VP)
    gesture = ctx.video_processor.last if ctx.video_processor else RPSMove.NONE
    st.write(f"Current gesture → **{gesture.value.upper()}**")
