# ----------------- gesture_utils.py -----------------
"""Common gesture detection utilities (single source of truth).

Uses Mediapipe Hands to classify ROCK/PAPER/SCISSORS based on finger state.
Includes GestureStabilizer to smooth out frame‑to‑frame noise.
"""

from collections import deque, Counter
from enum import Enum
from typing import Deque, Optional

import mediapipe as mp
import numpy as np

mp_hands = mp.solutions.hands

class RPSMove(str, Enum):
    ROCK = "rock"
    PAPER = "paper"
    SCISSORS = "scissors"
    NONE = "none"  # indeterminate / no hand


def _classify_from_landmarks(landmarks) -> RPSMove:
    """Return move based on landmarks geometry (simple heuristic)."""
    if landmarks is None:
        return RPSMove.NONE

    # Landmark indexes for fingertips (except thumb tip which uses x‑axis)
    fingertips = [8, 12, 16, 20]
    extended = 0
    for idx in fingertips:
        tip = landmarks.landmark[idx]
        pip = landmarks.landmark[idx - 2]
        if tip.y < pip.y:  # finger extended
            extended += 1

    thumb_tip = landmarks.landmark[4]
    thumb_ip = landmarks.landmark[3]
    thumb_extended = thumb_tip.x > thumb_ip.x

    if extended == 0 and not thumb_extended:
        return RPSMove.ROCK
    if extended == 4 and thumb_extended:
        return RPSMove.PAPER
    if extended == 2 and not thumb_extended:
        return RPSMove.SCISSORS
    return RPSMove.NONE


class GestureStabilizer:
    """Return the most frequent move over N recent frames."""

    def __init__(self, window: int = 10):
        self.window: Deque[RPSMove] = deque(maxlen=window)

    def update(self, move: RPSMove) -> RPSMove:
        self.window.append(move)
        if len(self.window) < self.window.maxlen:
            return RPSMove.NONE
        most_common, freq = Counter(self.window).most_common(1)[0]
        return most_common if freq > self.window.maxlen // 2 else RPSMove.NONE


__all__ = ["RPSMove", "GestureStabilizer", "_classify_from_landmarks"]
