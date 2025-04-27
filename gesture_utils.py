import cv2
import mediapipe as mp

mp_hands = mp.solutions.hands
hands = mp_hands.Hands(static_image_mode=False, max_num_hands=1, min_detection_confidence=0.7)
mp_draw = mp.solutions.drawing_utils

def get_finger_count(frame):
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    result = hands.process(rgb)
    gesture = "Tidak dikenali"
    annotated_frame = frame.copy()

    if result.multi_hand_landmarks and result.multi_handedness:
        hand = result.multi_hand_landmarks[0]
        handedness = result.multi_handedness[0].classification[0].label  # "Left" atau "Right"
        fingers = []

        # Thumb detection lebih akurat tergantung tangan kiri/kanan
        if handedness == "Right":
            if hand.landmark[4].x < hand.landmark[3].x:
                fingers.append(1)
            else:
                fingers.append(0)
        else:  # Tangan kiri
            if hand.landmark[4].x > hand.landmark[3].x:
                fingers.append(1)
            else:
                fingers.append(0)

        # 4 jari lainnya
        for tip in [8, 12, 16, 20]:
            if hand.landmark[tip].y < hand.landmark[tip - 2].y:
                fingers.append(1)
            else:
                fingers.append(0)

        count = sum(fingers)

        # Mapping jumlah jari ke gesture
        if count == 0:
            gesture = "Batu"
        elif count == 2:
            gesture = "Gunting"
        elif count == 5:
            gesture = "Kertas"
        else:
            gesture = "Tidak dikenali"

        # Gambar tangan
        mp_draw.draw_landmarks(annotated_frame, hand, mp_hands.HAND_CONNECTIONS)

        return gesture, annotated_frame

    return None, frame
