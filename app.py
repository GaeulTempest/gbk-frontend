import json, threading, asyncio, time, urllib.parse, requests, av, websockets, mediapipe as mp
import streamlit as st
from streamlit_webrtc import webrtc_streamer, WebRtcMode, VideoProcessorBase
from gesture_utils import RPSMove, GestureStabilizer, _classify_from_landmarks

API     = "https://web-production-7e17f.up.railway.app"
POLL    = 3
WS_PING = 20
AUTO_SUBMIT_DELAY = 5  # detik

st.set_page_config("RPS Gesture Game", "✊")
st.title("✊ Rock-Paper-Scissors Online")

# ───── session defaults ─────────────────────────────────
defaults = dict(
    game_id=None, player_id=None, role=None, player_name=None,
    players={}, _hash="", ws_thread=False, err=None,
    poll_ts=0, game_started=False, cam_ctx=None,
    detected_move=None, move_ts=0, move_sent=False
)
for k,v in defaults.items():
    st.session_state.setdefault(k, v)

# ───── HTTP helpers ───────────────────────────────────
def post(path, **data):
    try:
        r = requests.post(f"{API}{path}", json=data, timeout=15)
        r.raise_for_status()
        return r.json()
    except requests.RequestException as e:
        st.session_state.err = (
            e.response.text if getattr(e, "response", None) else str(e)
        )

def get_state(gid):
    try:
        r = requests.get(f"{API}/state/{gid}", timeout=10)
        if r.status_code == 200:
            return r.json()
    except:
        pass

def _h(pl): return json.dumps(pl, sort_keys=True)

def set_players(pl):
    if st.session_state.game_started:
        return
    h = _h(pl)
    if h != st.session_state._hash:
        st.session_state.players = pl
        st.session_state._hash    = h

# ========================================================
# LOBBY
# ========================================================
tab_lobby, tab_game = st.tabs(["🏠 Lobby", "🎮 Game"])
with tab_lobby:
    name = st.text_input("Your name", max_chars=20).strip()
    if name:
        st.session_state.player_name = name
    if not st.session_state.player_name:
        st.stop()

    cA, cB = st.columns(2)
    with cA:
        if st.button("Create Room"):
            res = post("/create_game", player_name=name)
            if res:
                st.session_state.update(res)
            else:
                st.error(st.session_state.err)
    with cB:
        room = st.text_input("Room ID")
        if st.button("Join Room") and room:
            res = post(f"/join/{urllib.parse.quote(room.strip())}", player_name=name)
            if res:
                st.session_state.update(res, game_id=room)
                snap = get_state(room)
                if snap:
                    set_players(snap["players"])
                else:
                    st.error(st.session_state.err or "Failed to fetch state")
            else:
                st.error(st.session_state.err or "Join failed")

    if st.session_state.game_id:
        st.success(
            f"Connected as **{st.session_state.player_name} "
            f"(Player {st.session_state.role})** | Room `{st.session_state.game_id}`"
        )

# ========================================================
# GAME
# ========================================================
with tab_game:
    gid = st.session_state.game_id
    if not gid:
        st.info("Create or join a room first."); st.stop()

    # ── LOBBY PHASE ──────────────────────────────────────
    if not st.session_state.game_started:

        # WebSocket listener untuk sinkron Ready
        if not st.session_state.ws_thread:
            WS_URI = API.replace("https","wss",1)+f"/ws/{gid}/{st.session_state.player_id}"
            def ws_loop():
                async def run():
                    while True:
                        try:
                            async with websockets.connect(WS_URI, ping_interval=WS_PING) as ws:
                                while True:
                                    data = json.loads(await ws.recv())
                                    set_players(data["players"])
                        except:
                            await asyncio.sleep(1)
                asyncio.run(run())
            threading.Thread(target=ws_loop, daemon=True).start()
            st.session_state.ws_thread = True

        # manual refresh jika perlu
        if st.button("🔄 Refresh status"):
            snap = get_state(gid)
            if snap:
                set_players(snap["players"])
            else:
                st.error(st.session_state.err or "Failed to fetch state")

        # tampilkan list & status
        pl = st.session_state.players
        c1, c2 = st.columns(2)
        for role, col in zip(("A","B"), (c1,c2)):
            p = pl.get(role,{})
            if p.get("name"):
                col.markdown(f"**{role} – {p['name']}**")
                col.write("✅ Ready" if p.get("ready") else "⏳ Not ready")
            else:
                col.write(f"*waiting Player {role}*")

        me_ready   = pl.get(st.session_state.role,{}).get("ready",False)
        both_ready = pl.get("A",{}).get("ready") and pl.get("B",{}).get("ready")

        if not me_ready:
            if st.button("I'm Ready", key=f"ready_{st.session_state.player_id}"):
                snap = post(f"/ready/{gid}", player_id=st.session_state.player_id)
                if snap: set_players(snap["players"])
                else:     st.error(st.session_state.err)

        if both_ready:
            if st.button("▶️ Start Game"):
                st.session_state.game_started = True

        st.info("Press Ready on both sides, then Start Game")

    # ── GAME PHASE ───────────────────────────────────────
    else:
        # inisialisasi kamera hanya sekali
        if st.session_state.cam_ctx is None:
            class VP(VideoProcessorBase):
                def __init__(self):
                    self.hands = mp.solutions.hands.Hands(max_num_hands=1)
                    self.stab  = GestureStabilizer()
                    self.last  = RPSMove.NONE

                def recv(self, frame):
                    img = frame.to_ndarray(format="bgr24")
                    res = self.hands.process(img[:,:,::-1])
                    mv  = (_classify_from_landmarks(res.multi_hand_landmarks[0])
                           if res and res.multi_hand_landmarks else RPSMove.NONE)
                    self.last = self.stab.update(mv)
                    return av.VideoFrame.from_ndarray(img, format="bgr24")

            st.session_state.cam_ctx = webrtc_streamer(
                key="cam",
                mode=WebRtcMode.SENDONLY,
                video_processor_factory=VP,
                async_processing=True
            )

        # live feedback
        ctx     = st.session_state.cam_ctx
        gesture = ctx.video_processor.last if ctx and ctx.video_processor else RPSMove.NONE
        st.write(f"Live gesture → **{gesture.value.upper()}**")

        # reset jika kembali NONE
        if gesture == RPSMove.NONE:
            st.session_state.detected_move = None
            st.session_state.move_ts      = 0
            st.session_state.move_sent    = False
        else:
            now = time.time()
            if st.session_state.detected_move != gesture:
                st.session_state.detected_move = gesture
                st.session_state.move_ts      = now
                st.session_state.move_sent    = False
            elif not st.session_state.move_sent and now - st.session_state.move_ts >= AUTO_SUBMIT_DELAY:
                # auto-submit
                snap = post(f"/move/{gid}",
                            player_id=st.session_state.player_id,
                            move=gesture.value)
                st.session_state.move_sent = True
                st.success(f"Sent **{gesture.value.upper()}**!")

