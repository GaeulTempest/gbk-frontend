import streamlit as st
import requests
import cv2
from gesture_utils import get_finger_count

# ✅ URL backend dari Railway
BASE_URL = "https://web-production-7e17f.up.railway.app"

st.title("🕹️ Gunting Batu Kertas - Multiplayer Online")
player = st.selectbox("Pilih peran", ["A", "B"])
frame_window = st.image([])

# Buka kamera
cap = cv2.VideoCapture(0)
gesture = None

st.info("Tunjukkan gesture tanganmu ke kamera...")

while True:
    ret, frame = cap.read()
    if not ret:
        st.error("Kamera tidak terdeteksi.")
        break

    frame = cv2.flip(frame, 1)
    result, processed_frame = get_finger_count(frame)

    if result:
        cv2.putText(processed_frame, f"{result}", (50, 100),
                    cv2.FONT_HERSHEY_SIMPLEX, 2, (0, 255, 0), 3)
        gesture = result

    frame_window.image(cv2.cvtColor(processed_frame, cv2.COLOR_BGR2RGB))

    if gesture in ["Batu", "Gunting", "Kertas"]:
        if st.button("📤 Kirim Gerakan"):
            try:
                response = requests.post(f"{BASE_URL}/submit",
                                         json={"player": player, "move": gesture})
                if response.status_code == 200:
                    st.success(f"Gerakan '{gesture}' dikirim sebagai Player {player}")
                else:
                    st.error("Gagal mengirim gerakan ke server.")
            except Exception as e:
                st.error(f"Terjadi kesalahan: {e}")
            break

cap.release()

# Tombol lihat hasil
if st.button("📊 Lihat Hasil"):
    try:
        res = requests.get(f"{BASE_URL}/result").json()
        if "result" in res:
            st.write(f"🧍 Player A: {res['A']} | 🧍 Player B: {res['B']}")
            st.success(f"🏆 Hasil: {res['result']}")
        else:
            st.warning("Menunggu lawan bermain...")
    except Exception as e:
        st.error(f"Gagal mengakses server: {e}")
