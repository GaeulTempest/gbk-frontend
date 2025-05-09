import json, threading, asyncio, time, urllib.parse, requests, av, websockets, mediapipe as mp
import streamlit as st
from streamlit_webrtc import webrtc_streamer, WebRtcMode, VideoProcessorBase
from gesture_utils import RPSMove, GestureStabilizer, _classify_from_landmarks

API = "https://web-production-7e17f.up.railway.app"

st.set_page_config("RPS Gesture Game", "✊")
st.title("✊ Rock-Paper-Scissors Online")

# default keys
for k in ("game_id","player_id","role","player_name",
          "players","_hash","ws_thread","err","poll_ts"):
    st.session_state.setdefault(k, None)

# ---------- HTTP helpers ----------
def post(path, **data):
    try:
        r = requests.post(f"{API}{path}", json=data, timeout=15); r.raise_for_status()
        return r.json()
    except requests.RequestException as e:
        st.session_state.err = e.response.text if getattr(e, "response", None) else str(e)
        return None

def get_state(gid):
    try:
        r = requests.get(f"{API}/state/{gid}", timeout=10)
        if r.status_code == 200: return r.json()
    except: pass

def _h(pl): return json.dumps(pl, sort_keys=True)
def set_players(pl):
    st.session_state.players = pl
    st.session_state._hash   = _h(pl)

# =========================================================
#  LOBBY
# =========================================================
tab_lobby, tab_game = st.tabs(["🏠 Lobby","🎮 Game"])

with tab_lobby:
    name = st.text_input("Your name", max_chars=20).strip()
    if name: st.session_state.player_name = name
    if not st.session_state.player_name: st.stop()

    colA, colB = st.columns(2)

    # ----- Create
    with colA:
        if st.button("Create Room"):
            res = post("/create_game", player_name=name)
            if res: st.session_state.update(res)
            else:   st.error(st.session_state.err)

    # ----- Join
    with colB:
        room_id = st.text_input("Room ID")
        if st.button("Join Room") and room_id:
            res = post(f"/join/{urllib.parse.quote(room_id.strip())}",
                       player_name=name)
            if res:
                st.session_state.update(res, game_id=room_id)
                snap = get_state(room_id)
                if snap: set_players(snap["players"])
            else: st.error(st.session_state.err)

    if st.session_state.game_id:
        st.success(f"Connected as **{st.session_state.player_name} "
                   f"(Player {st.session_state.role})**  |  "
                   f"Room `{st.session_state.game_id}`")

# =========================================================
#  GAME
# =========================================================
with tab_game:
    gid = st.session_state.game_id
    if not gid:
        st.info("Create or join a room first."); st.stop()

    WS_URI = API.replace("https","wss",1)+f"/ws/{gid}/{st.session_state.player_id}"
    st.caption(f"WS → {WS_URI}")

    # ---------- WebSocket listener ----------
    if not st.session_state.ws_thread:
        def run_ws():
            async def loop():
                while True:
                    try:
                        async with websockets.connect(WS_URI, ping_interval=20) as ws:
                            while True:
                                data = json.loads(await ws.recv())
                                if _h(data["players"]) != st.session_state._hash:
                                    set_players(data["players"])
                                    st.experimental_rerun()
                    except: await asyncio.sleep(1)
        threading.Thread(target=lambda: asyncio.run(run_ws()), daemon=True).start()
        st.session_state.ws_thread = True

    # ---------- Player panel ----------
    players = st.session_state.get("players") or {}
    colA, colB = st.columns(2)
    for role, col in zip(("A","B"), (colA,colB)):
        p = players.get(role)
        if p and p.get("name"):
            col.markdown(f"**{role} – {p['name']}**")
            col.write("✅ Ready" if p.get("ready") else "⏳ Not ready")
        else: col.write(f"*waiting Player {role}*")

    me_role   = st.session_state.role
    me_ready  = players.get(me_role, {}).get("ready", False)
    both_ready= players.get("A",{}).get("ready") and players.get("B",{}).get("ready")

    # ---------- Ready button ----------
    if not me_ready:
        if st.button("I'm Ready", key=f"ready_{st.session_state.player_id}"):
            snap = post(f"/ready/{gid}", player_id=st.session_state.player_id)
            if snap: set_players(snap["players"])
            else:    st.error(st.session_state.err)

    # ---------- Polling fallback ----------
    if not both_ready and time.time() - (st.session_state.poll_ts or 0) > 3:
        st.session_state.poll_ts = time.time()
        snap = get_state(gid)
        if snap and _h(snap["players"]) != st.session_state._hash:
            set_players(snap["players"]); st.experimental_rerun()

    if not both_ready:
        st.info("Waiting until **both players** press *I'm Ready*…")
        st.stop()

    st.success("Both players ready – game starts!")

    # ---------- Webcam & gesture ----------
    class VP(VideoProcessorBase):
        def __init__(self):
            self.hands = mp.solutions.hands.Hands(max_num_hands=1)
            self.stab  = GestureStabilizer(); self.last = RPSMove.NONE
        def recv(self, frame):
            img = frame.to_ndarray(format="bgr24")
            res = self.hands.process(img[:,:,::-1])
            mv  = _classify_from_landmarks(res.multi_hand_landmarks[0]) if res.multi_hand_landmarks else RPSMove.NONE
            self.last = self.stab.update(mv)
            return av.VideoFrame.from_ndarray(img, format="bgr24")

    ctx = webrtc_streamer(key="cam",
                          mode=WebRtcMode.SENDONLY,
                          video_processor_factory=VP)
    gest = ctx.video_processor.last if ctx.video_processor else RPSMove.NONE
    st.write(f"Current gesture → **{gest.value.upper()}**")
