import json, threading, asyncio, time, urllib.parse, requests, av, websockets, mediapipe as mp
import streamlit as st
from streamlit_webrtc import webrtc_streamer, WebRtcMode, VideoProcessorBase
from gesture_utils import RPSMove, GestureStabilizer, _classify_from_landmarks

API = "https://web-production-7e17f.up.railway.app"

st.set_page_config("RPS Gesture Game", "✊")
st.title("✊ Rock-Paper-Scissors Online")

# ── default session values
for k in ("game_id","player_id","role","player_name",
          "players","_players_hash","ws_thread","last_error","poll_ts"):
    st.session_state.setdefault(k, None)

# ------------------------------------------------------------------
# helper http
def api_post(path, **payload):
    try:
        r = requests.post(f"{API}{path}", json=payload, timeout=15)
        r.raise_for_status()
        return r.json()
    except requests.HTTPError as e:
        st.session_state.last_error = e.response.text if e.response else str(e)
    except requests.RequestException as e:
        st.session_state.last_error = str(e)
    return None

def api_get_state(gid):
    try:
        r = requests.get(f"{API}/state/{gid}", timeout=10)
        if r.status_code == 200:
            return r.json()
    except: pass
    return None

def hash_players(pl): return json.dumps(pl, sort_keys=True)

def set_players(new_pl):
    h = hash_players(new_pl)
    if h != st.session_state._players_hash:
        st.session_state.players = new_pl
        st.session_state._players_hash = h
        st.experimental_rerun()

# ------------------------------------------------------------------
# Lobby tab
tab_lobby, tab_game = st.tabs(["🏠 Lobby","🎮 Game"])
with tab_lobby:
    name = st.text_input("Your name", max_chars=20).strip()
    if name:
        st.session_state.player_name = name
    if not st.session_state.player_name:
        st.stop()

    cA, cB = st.columns(2)

    # Create room
    with cA:
        if st.button("Create Room"):
            res = api_post("/create_game", player_name=name)
            if res:
                st.session_state.update(res)
            else:
                st.error(f"Create failed: {st.session_state.last_error}")

    # Join room
    with cB:
        room = st.text_input("Room ID")
        if st.button("Join Room") and room:
            res = api_post(f"/join/{urllib.parse.quote(room.strip())}",
                           player_name=name)
            if res:
                st.session_state.update(res, game_id=room)
            else:
                st.error(f"Join failed: {st.session_state.last_error}")

    if st.session_state.game_id:
        st.success(f"Connected as **{st.session_state.player_name} "
                   f"(Player {st.session_state.role})**"
                   f"  |  Room `{st.session_state.game_id}`")

# ------------------------------------------------------------------
# Game tab
with tab_game:
    gid = st.session_state.game_id
    if not gid:
        st.info("Create or join a room first."); st.stop()

    # -- WebSocket URI
    WS_URI = API.replace("https","wss",1)+f"/ws/{gid}/{st.session_state.player_id}"
    st.caption(f"WS → {WS_URI}")

    # -- WebSocket listener (one thread, auto-reconnect)
    if not st.session_state.ws_thread:
        def launch():
            async def ws_loop():
                while True:
                    try:
                        async with websockets.connect(WS_URI, ping_interval=20) as ws:
                            while True:
                                data = json.loads(await ws.recv())
                                set_players(data["players"])
                    except:
                        await asyncio.sleep(1)
            threading.Thread(target=lambda: asyncio.run(ws_loop()),
                             daemon=True).start()
            st.session_state.ws_thread = True
        launch()

    players = st.session_state.get("players") or {}
    colA,colB = st.columns(2)
    for role, col in zip(("A","B"), (colA,colB)):
        p = players.get(role)
        if p and p.get("name"):
            col.markdown(f"**{role} – {p['name']}**")
            col.write("✅ Ready" if p.get("ready") else "⏳ Not ready")
        else:
            col.write(f"*waiting Player {role}*")

    my_role   = st.session_state.role
    my_ready  = players.get(my_role, {}).get("ready", False)
    both_ready = players.get("A",{}).get("ready") and players.get("B",{}).get("ready")

    # Ready button
    if not my_ready:
        if st.button("I'm Ready", key=f"ready_{st.session_state.player_id}"):
            snap = api_post(f"/ready/{gid}", player_id=st.session_state.player_id)
            if snap:
                set_players(snap["players"])
            else:
                st.error(f"Ready failed: {st.session_state.last_error}")

    # fallback polling tiap 3 dtk bila saya Ready tapi kedua belum
    if my_ready and not both_ready and time.time() - (st.session_state.poll_ts or 0) > 3:
        st.session_state.poll_ts = time.time()
        snap = api_get_state(gid)
        if snap: set_players(snap["players"])

    if not both_ready:
        st.info("Waiting until **both players** press *I'm Ready*…")
        st.stop()

    st.success("Both players ready – game starts!")

    # -------- webcam & live gesture ----------
    class VP(VideoProcessorBase):
        def __init__(self):
            self.hands = mp.solutions.hands.Hands(max_num_hands=1)
            self.stab  = GestureStabilizer(); self.last = RPSMove.NONE
        def recv(self, frame):
            img = frame.to_ndarray(format="bgr24")
            res = self.hands.process(img[:,:,::-1])
            move = _classify_from_landmarks(res.multi_hand_landmarks[0]) \
                   if res.multi_hand_landmarks else RPSMove.NONE
            self.last = self.stab.update(move)
            return av.VideoFrame.from_ndarray(img, format="bgr24")

    ctx = webrtc_streamer(key="cam", mode=WebRtcMode.SENDONLY,
                          video_processor_factory=VP)
    gest = ctx.video_processor.last if ctx.video_processor else RPSMove.NONE
    st.write(f"Current gesture → **{gest.value.upper()}**")
