import cv2
import mediapipe as mp

mp_hands = mp.solutions.hands
hands = mp_hands.Hands(static_image_mode=False, max_num_hands=1)
mp_draw = mp.solutions.drawing_utils

def get_finger_count(frame):
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    result = hands.process(rgb)
    gesture = "Tidak dikenali"
    annotated_frame = frame.copy()

    if result.multi_hand_landmarks:
        hand = result.multi_hand_landmarks[0]
        fingers = []

        # Thumb
        if hand.landmark[4].x < hand.landmark[3].x:
            fingers.append(1)
        else:
            fingers.append(0)

        # 4 Jari lainnya
        for tip in [8, 12, 16, 20]:
            if hand.landmark[tip].y < hand.landmark[tip - 2].y:
                fingers.append(1)
            else:
                fingers.append(0)

        count = sum(fingers)
        gesture = {
            0: "Batu",
            2: "Gunting",
            5: "Kertas"
        }.get(count, "Tidak dikenali")

        # Gambar tangan
        mp_draw.draw_landmarks(annotated_frame, hand, mp_hands.HAND_CONNECTIONS)

        return gesture, annotated_frame

    return None, frame
