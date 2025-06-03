import json, threading, asyncio, time, urllib.parse, requests, av, websockets, mediapipe as mp
import streamlit as st
from streamlit_webrtc import webrtc_streamer, WebRtcMode, VideoProcessorBase
from gesture_utils import RPSMove, GestureStabilizer, _classify_from_landmarks

API = "https://web-production-7e17f.up.railway.app"
WS_PING = 20
AUTO_SUBMIT_DELAY = 5  # detik gesture stabil sebelum auto-submit

st.set_page_config("RPS Gesture Game", "✊")
st.title("✊ Rock-Paper-Scissors Online")

# ── Inisialisasi session_state ─────────────────────────
defaults = dict(
    game_id=None, player_id=None, role=None, player_name=None,
    players={}, _hash="", ws_thread=False, err=None,
    move_ts=0, detected_move=None, move_sent=False,
    cam_ctx=None, game_started=False
)
for k, v in defaults.items():
    st.session_state.setdefault(k, v)

# ── Helper HTTP ────────────────────────────────────────
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
        r.raise_for_status()
        return r.json()
    except Exception as e:
        st.session_state.err = f"Failed to get state: {str(e)}"
        return None

def _h(pl): 
    return json.dumps(pl, sort_keys=True)

def set_players(pl):
    """Update hanya di fase LOBBY."""
    if st.session_state.game_started:
        return
    h = _h(pl)
    if h != st.session_state._hash:
        st.session_state.players = pl
        st.session_state._hash = h

# =========================================================
#  LOBBY SECTION
# =========================================================
tab_lobby, tab_player, tab_game = st.tabs(["🏠 Lobby", "👾 Player", "🎮 Game"])

with tab_lobby:
    name = st.text_input("Your name", max_chars=20).strip()
    if name:
        st.session_state.player_name = name

    if not st.session_state.player_name:
        st.warning("Enter your name to continue.")
        st.stop()

    cA, cB = st.columns(2)

    # Create Room
    with cA:
        if st.button("Create Room"):
            res = post("/create_game", player_name=name)
            if res:
                st.session_state.update(res)
                st.session_state.game_started = False
                st.session_state.cam_ctx = None
                st.session_state.detected_move = None
                st.session_state.move_ts = 0
                st.session_state.move_sent = False
            else:
                st.error(st.session_state.err or "Create failed")

    # Join Room
    with cB:
        room = st.text_input("Room ID").strip()
        if st.button("Join Room") and room:
            res = post(f"/join/{urllib.parse.quote(room)}", player_name=name)
            if res:
                st.session_state.update(
                    game_id=room,
                    player_id=res.get("player_id"),
                    role=res.get("role")
                )
                st.session_state.game_started = False
                st.session_state.cam_ctx = None
                st.session_state.detected_move = None
                st.session_state.move_ts = 0
                st.session_state.move_sent = False
                snap = get_state(room)
                if snap:
                    set_players(snap.get("players", {}))
                else:
                    st.error(st.session_state.err or "Failed to get initial game state")
            else:
                st.error(st.session_state.err or "Join failed")

    if not st.session_state.game_id:
        st.info("Create or join a room to continue.")
        st.stop()

    st.success(
        f"Connected as **{st.session_state.player_name} "
        f"(Player {st.session_state.role})** | Room `{st.session_state.game_id}`"
    )

# =========================================================
#  PLAYER SECTION
# =========================================================
with tab_player:
    pl = st.session_state.players
    c1, c2 = st.columns(2)
    for role, col in zip(("A", "B"), (c1, c2)):
        p = pl.get(role, {})
        if p.get("name"):
            col.markdown(f"**{role} – {p['name']}**")
            col.write("✅ Ready" if p.get("ready") else "⏳ Not ready")
        else:
            col.write(f"*waiting Player {role}*")

    me_ready = pl.get(st.session_state.role, {}).get("ready", False)
    both_ready = pl.get("A", {}).get("ready") and pl.get("B", {}).get("ready")

    # Pemain tekan tombol Ready
    if not me_ready:
        if st.button("I'm Ready", key=f"ready_{st.session_state.player_id}"):
            snap = post(f"/ready/{st.session_state.game_id}", player_id=st.session_state.player_id)
            if snap:
                set_players(snap["players"])
                st.session_state.players = snap["players"]
            else:
                st.error(st.session_state.err or "Ready failed")

    # Tombol untuk Refresh Status (lebih kecil, hanya ikon 🔄)
    st.write("")  # spacer
    refresh_col, _ = st.columns([1, 4])
    with refresh_col:
        if st.button("🔄"):
            snap = get_state(st.session_state.game_id)
            if snap:
                set_players(snap["players"])
                st.session_state.players = snap["players"]
            else:
                st.error(st.session_state.err or "Failed to refresh status")

    # Jika kedua pemain sudah ready, tampilkan notifikasi sukses dan setel game_started = True
    if both_ready:
        st.success("🎉 Semua pemain sudah READY! Silakan beralih ke tab Game.")
        # Setel game_started menjadi True setelah kedua pemain ready
        st.session_state.game_started = True
    else:
        st.info("Kedua pemain harus menekan READY sebelum memulai game.")

# =========================================================
#  GAME SECTION
# =========================================================
with tab_game:
    if not st.session_state.game_started:
        st.warning("The game will start once both players are ready.")
        st.stop()

    # Menampilkan perangkat kamera menggunakan webrtc_streamer
    st.write("### Pilih Perangkat Kamera")
    
    # Penggunaan webrtc_streamer secara langsung
    st.session_state.cam_ctx = webrtc_streamer(
        key="cam",
        mode=WebRtcMode.SENDONLY,
        video_processor_factory=VideoProcessorBase,
        async_processing=True
    )
    
    st.info("Tekan **Start Game** untuk memulai permainan!")
