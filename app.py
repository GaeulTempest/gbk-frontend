import streamlit as st
import requests
import cv2
from gesture_utils import get_finger_count

st.title("🕹️ Gunting Batu Kertas - Multiplayer Online")

player = st.selectbox("Pilih peran", ["A", "B"])
frame_window = st.image([])

cap = cv2.VideoCapture(0)

gesture = None

st.info("Tunjukkan gesture tanganmu ke kamera...")

while True:
    ret, frame = cap.read()
    frame = cv2.flip(frame, 1)

    result, hand = get_finger_count(frame)

    if result:
        cv2.putText(frame, f"{result}", (50, 100), cv2.FONT_HERSHEY_SIMPLEX, 2, (0, 255, 0), 3)
        gesture = result

    frame_window.image(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))


    if gesture in ["Batu", "Gunting", "Kertas"]:
        if st.button("Kirim Gerakan"):
            requests.post("http://localhost:5000/submit", json={"player": player, "move": gesture})
            st.success(f"Gerakan '{gesture}' dikirim sebagai Player {player}")
            break

cap.release()

if st.button("Lihat Hasil"):
    res = requests.get("http://localhost:5000/result").json()
    if "result" in res:
        st.write(f"🧍 Player A: {res['A']} | 🧍 Player B: {res['B']}")
        st.success(f"🏆 Hasil: {res['result']}")
    else:
        st.warning("Menunggu lawan bermain...")
