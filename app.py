# ... (kode di atas tidak berubah) ...

    # ------------------------------------------------------------------
    # Camera section ----------------------------------------------------
    # Buat komponen kamera sekali saja, simpan di session_state
    if "cam_ctx" not in st.session_state:
        class VP(VideoProcessorBase):
            def __init__(self):
                self.hands = mp.solutions.hands.Hands(max_num_hands=1)
                self.stab  = GestureStabilizer(); self.last_move = RPSMove.NONE
            def recv(self, frame):
                img = frame.to_ndarray(format="bgr24")
                res = self.hands.process(img[:,:,::-1])
                mv  = _classify_from_landmarks(res.multi_hand_landmarks[0]) \
                      if res and res.multi_hand_landmarks else RPSMove.NONE
                self.last_move = self.stab.update(mv)
                return av.VideoFrame.from_ndarray(img, format="bgr24")

        st.session_state.cam_ctx = webrtc_streamer(
            key="cam",
            mode=WebRtcMode.SENDONLY,
            video_processor_factory=VP,
        )

    # Ambil context yang sudah ada
    ctx = st.session_state.cam_ctx
    gest = ctx.video_processor.last_move if ctx and ctx.video_processor else RPSMove.NONE
    st.write(f"Current gesture → **{gest.value.upper()}**")
