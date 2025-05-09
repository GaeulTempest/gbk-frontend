import json, threading, asyncio, time, urllib.parse, requests, av, websockets, mediapipe as mp
import streamlit as st
from streamlit_webrtc import webrtc_streamer, WebRtcMode, VideoProcessorBase
from gesture_utils import RPSMove, GestureStabilizer, _classify_from_landmarks

API = "https://web-production-7e17f.up.railway.app"

st.set_page_config("RPS Gesture Game", "✊")
st.title("✊ Rock-Paper-Scissors Online")

# ── session defaults ─────────────────────────────────────
for k in ("game_id","player_id","role","player_name",
          "players","_players_hash","ws_thread","last_error"):
    st.session_state.setdefault(k, None)

# ── helper HTTP call with graceful error -----------------
def api_post(path, **payload):
    url = f"{API}{path}"
    try:
        r = requests.post(url, json=payload, timeout=15)
        r.raise_for_status()
        return r.json()
    except requests.HTTPError as e:
        st.session_state.last_error = e.response.text if e.response else str(e)
        return None
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

def players_hash(pl):            # deterministic string repr
    return json.dumps(pl, sort_keys=True)

def update_players(new_pl):
    h = players_hash(new_pl)
    if h != st.session_state.get("_players_hash"):
        st.session_state.players = new_pl
        st.session_state._players_hash = h
        st.experimental_rerun()

# ── UI: tabs ------------------------------------------------------
tab_lobby, tab_game = st.tabs(["🏠 Lobby", "🎮 Game"])

# =========================================================
#  LOBBY
# =========================================================
with tab_lobby:
    name = st.text_input("Your name", max_chars=20).strip()
    if name:
        st.session_state.player_name = name
    if not st.session_state.player_name:
        st.stop()

    col_create, col_join = st.columns(2)

    # ---- Create Room
    with col_create:
        if st.button("Create Room"):
            res = api_post("/create_game", player_name=name)
            if res:
                st.session_state.update(res)
            else:
                st.error(f"Create failed: {st.session_state.last_error}")

    # ---- Join Room
    with col_join:
        room = st.text_input("Room ID")
        if st.button("Join Room") and room:
            res = api_post(f"/join/{urllib.parse.quote(room.strip())}",
                           player_name=name)
            if res is None:
                st.error(f"Join failed: {st.session_state.last_error}")
            else:
                st.session_state.update(res, game_id=room)

    gid = st.session_state.game_id
    if gid:
        st.success(f"Connected as **{st.session_state.player_name} "
                   f"(Player {st.session_state.role})**  |  Room `{gid}`")

# =========================================================
#  GAME
# =========================================================
with tab_game:
    gid = st.session_state.game_id
    if not gid:
        st.info("Create or join a room first."); st.stop()

    WS_URI = API.replace("https","wss",1)+f"/ws/{gid}/{st.session_state.player_id}"
    st.caption(f"WS → {WS_URI}")

    # -------- WebSocket listener (auto-reconnect) ----------
    if not st.session_state.ws_thread:
        async def ws_loop():
            while True:
                try:
                    async with websockets.connect(WS_URI, ping_interval=20) as ws:
                        while True:
                            data = json.loads(await ws.recv())
                            update_players(data["players"])
                except:
                    await asyncio.sleep(1)     # reconnect delay
        threading.Thread(target=lambda: asyncio.run(ws_loop()),
                         daemon=True).start()
        st.session_state.ws_thread = True

    # -------- players panel -------------------------------
    players = st.session_state.get("players") or {}
    colA, colB = st.columns(2)
    for role, col in zip(("A","B"), (colA, colB)):
        p = players.get(role)
        if p and p.get("name"):
            col.markdown(f"**{role} – {p['name']}**")
            col.write("✅ Ready" if p.get("ready") else "⏳ Not ready")
        else:
            col.write(f"*waiting Player {role}*")

    my_role     = st.session_state.role
    my_ready    = players.get(my_role, {}).get("ready", False)
    both_ready  = players.get("A",{}).get("ready") and players.get("B",{}).get("ready")

    # -------- Ready button --------------------------------
    if not my_ready:
        if st.button("I'm Ready", key=f"ready_{st.session_state.player_id}"):
            snap = api_post(f"/ready/{gid}", player_id=st.session_state.player_id)
            if snap:
                update_players(snap["players"])
            else:
                st.error(f"Ready failed: {st.session_state.last_error}")

    # fallback polling 3-detik bila broadcast tak diterima
    if my_ready and not both_ready:
        if time.time() - st.session_state.get("poll_ts", 0) > 3:
            st.session_state.poll_ts = time.time()
            snap = api_get_state(gid)
            if snap: update_players(snap["players"])

    if not both_ready:
        st.info("Waiting until **both players** press *I'm Ready*…")
        st.stop()

    st.success("Both players ready – game starts!")

    # -------- Webcam & live gesture -----------------------
    class VP(VideoProcessorBase):
        def __init__(self):
            self.hands = mp.solutions.hands.Hands(max_num_hands=1)
            self.stab  = GestureStabilizer(); self.last = RPSMove.NONE
        def recv(self, frame):
            img = frame.to_ndarray(format="bgr24")
            res = self.hands.process(img[:, :, ::-1])
            move = _classify_from_landmarks(res.multi_hand_landmarks[0]) \
                   if res.multi_hand_landmarks else RPSMove.NONE
            self.last = self.stab.update(move)
            return av.VideoFrame.from_ndarray(img, format="bgr24")

    ctx = webrtc_streamer(key="cam",
                          mode=WebRtcMode.SENDONLY,
                          video_processor_factory=VP)
    gesture = ctx.video_processor.last if ctx.video_processor else RPSMove.NONE
    st.write(f"Current gesture → **{gesture.value.upper()}**")
