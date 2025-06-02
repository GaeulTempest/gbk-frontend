import streamlit as st
import requests
import json
import time
from streamlit_webrtc import webrtc_streamer, WebRtcMode

API_URL = os.getenv("API_URL", "http://localhost:8000")
WS_URL = API_URL.replace("http", "ws", 1)

st.set_page_config("Game Room", "🎮")
st.title("🎮 Multiplayer Game Lobby")

if "player" not in st.session_state:
    st.session_state.player = {"name": "", "room": None}

def refresh_rooms():
    try:
        res = requests.get(f"{API_URL}/list-rooms")
        st.session_state.rooms = res.json()["rooms"]
    except:
        st.error("Gagal memuat room")

# Form Nama Pemain
with st.expander("🏷️ Set Nama Pemain", expanded=not st.session_state.player["name"]):
    name = st.text_input("Nama Anda", max_chars=20)
    if st.button("Simpan Nama"):
        st.session_state.player["name"] = name.strip()
        st.rerun()

if not st.session_state.player["name"]:
    st.warning("Harap masukkan nama Anda terlebih dahulu")
    st.stop()

# Tab Utama
tab1, tab2 = st.tabs(["🏠 Lobby Room", "🎮 Game Room"])

with tab1:
    st.header("Daftar Room Tersedia")
    refresh = st.button("🔄 Refresh")
    if refresh:
        refresh_rooms()
    
    cols = st.columns([1, 2, 2, 1, 2])
    cols[0].write("**ID**")
    cols[1].write("**Pemilik**")
    cols[2].write("**Pemain**")
    cols[3].write("**Status**")
    cols[4].write("**Aksi**")
    
    if "rooms" not in st.session_state:
        refresh_rooms()
        
    for room in st.session_state.rooms:
        cols = st.columns([1, 2, 2, 1, 2])
        cols[0].code(room["id"][:6])
        cols[1].write(room["owner"])
        cols[2].write(f"{room['players']}/{room['max_players']}")
        cols[3].code(room["status"])
        
        if cols[4].button("Join", key=f"join_{room['id']}"):
            res = requests.post(
                f"{API_URL}/join-room/{room['id']}",
                json={"playerName": st.session_state.player["name"]}
            )
            if res.status_code == 200:
                st.session_state.player["room"] = res.json()["room"]
                st.rerun()
            else:
                st.error("Gagal masuk room")

    st.divider()
    with st.form("Buat Room Baru"):
        max_players = st.number_input("Maks Pemain", 2, 8, 4)
        if st.form_submit_button("Buat Room Baru"):
            res = requests.post(
                f"{API_URL}/create-room",
                json={"playerName": st.session_state.player["name"]}
            )
            st.session_state.player["room"] = res.json()["room"]
            st.rerun()

with tab2:
    if not st.session_state.player.get("room"):
        st.info("Pilih atau buat room di tab Lobby")
        st.stop()
        
    room = st.session_state.player["room"]
    st.header(f"Room {room['id'][:6]}")
    st.subheader(f"Pemilik: {room['owner']}")
    
    webrtc_ctx = webrtc_streamer(
        key="cam",
        mode=WebRtcMode.SENDRECV,
        media_stream_constraints={"video": True, "audio": False},
    )
    
    if room and room["status"] == "waiting":
        with st.expander("👥 Daftar Pemain"):
            for player in room["players"]:
                st.markdown(f"- {player}")
            
        if len(room["players"]) >= room["max_players"]:
            if st.button("🚀 Mulai Game"):
                room["status"] = "playing"
                requests.post(f"{API_URL}/update-room", json=room)
    
    st.markdown("""
    <style>
        section[data-testid="stSidebar"] {
            width: 400px !important;
        }
    </style>
    """, unsafe_allow_html=True)
