"""Fireball sequence state and procedural OpenCV flame rendering."""
import math
import random

import cv2
import numpy as np

from face_track import head_rotation

FIREBALL_SIGNS = ("serpent", "ram", "monkey", "boar", "horse", "tiger")
SIGN_HOLD = 0.3
SEQUENCE_TIMEOUT = 12.0
MOUTH_HOLD = 0.1
FIRE_DURATION = 1.5


class FireballJutsu:
    def __init__(self):
        self.reset()
        self.particles = []
        self.last_frame = None

    def reset(self):
        self.progress = 0
        self.candidate = None
        self.candidate_since = None
        self.last_step = None
        self.mouth_since = None
        self.fire_until = None

    def update(self, sign, near_mouth, now):
        if self.fire_until is not None:
            if now < self.fire_until:
                return "Fireball Jutsu!"
            self.reset()
        if self.last_step is not None and now - self.last_step > SEQUENCE_TIMEOUT:
            self.reset()
        if self.progress == len(FIREBALL_SIGNS):
            if near_mouth:
                if self.mouth_since is None:
                    self.mouth_since = now
                if now - self.mouth_since >= MOUTH_HOLD:
                    self.fire_until = now + FIRE_DURATION
                    return "Fireball Jutsu!"
                return f"Hold fingers near mouth: {max(0, MOUTH_HOLD - (now - self.mouth_since)):.1f}s"
            self.mouth_since = None
            return f"Ready! Bring fingertips to your mouth and hold {MOUTH_HOLD:g} seconds"
        if sign in ("Unknown", "No hands"):
            self.candidate = None
            self.candidate_since = None
        elif sign != self.candidate:
            self.candidate = sign
            self.candidate_since = now
        elif now - self.candidate_since >= SIGN_HOLD:
            expected = FIREBALL_SIGNS[self.progress]
            previous = FIREBALL_SIGNS[self.progress - 1] if self.progress else None
            if sign == expected:
                self.progress += 1
                self.last_step = now
                if self.progress == len(FIREBALL_SIGNS):
                    return f"Ready! Bring fingertips to your mouth and hold {MOUTH_HOLD:g} seconds"
            elif sign != previous:
                self.progress = 1 if sign == FIREBALL_SIGNS[0] else 0
                self.last_step = now if self.progress else None
                self.mouth_since = None
        return f"Fireball {self.progress}/6 | Next: {FIREBALL_SIGNS[self.progress]}"

    def firing(self, now):
        return self.fire_until is not None and now < self.fire_until

    def draw(self, frame, mouth, forward, face_width, now):
        """Emit glowing flame particles outward from the tracked mouth."""
        dt = min(0.1, max(0, now - self.last_frame)) if self.last_frame is not None else 0
        self.last_frame = now
        emitting = self.firing(now) and mouth is not None
        if emitting:
            direction = np.array([forward[0], -forward[1]], dtype=float)
            # Keep projected magnitude: a frontal face aims toward the viewer,
            # while a turned face produces a longer sideways flame stream.
            projection = float(np.linalg.norm(direction))
            perpendicular = (np.array([-direction[1], direction[0]]) / projection
                             if projection > 1e-6 else np.array([1.0, 0.0]))
            toward_viewer = max(0.0, float(forward[2]))
            scale = max(40, face_width)
            for _ in range(max(1, int(900 * dt))):
                speed = random.uniform(6.0, 10.0) * scale
                spread = random.uniform(-0.22, 0.22) * scale
                angle = random.uniform(0, math.tau)
                expansion = np.array([math.cos(angle), math.sin(angle)]) * speed * 0.10 * toward_viewer
                self.particles.append({"position": np.array(mouth, dtype=float),
                                       "velocity": direction * speed + perpendicular * spread * projection + expansion,
                                       "born": now, "life": random.uniform(0.5, 0.9),
                                       "size": random.uniform(0.035, 0.065) * scale})
        self.particles[:] = [p for p in self.particles if now - p["born"] < p["life"]]
        layer = np.zeros_like(frame)
        for particle in self.particles:
            age = now - particle["born"]
            phase = age / particle["life"]
            particle["position"] += particle["velocity"] * dt
            particle["velocity"][1] -= 12 * dt
            point = tuple(int(v) for v in particle["position"])
            radius = max(1, int(particle["size"] * (1 + phase) * (1 - phase)))
            color = (0, int(210 * (1 - phase)), int(255 * (1 - phase * 0.6)))
            cv2.circle(layer, point, radius, color, -1, cv2.LINE_AA)
            if phase < 0.35:
                cv2.circle(layer, point, max(1, radius // 2), (130, 245, 255), -1, cv2.LINE_AA)
        if self.particles:
            glow = cv2.GaussianBlur(layer, (0, 0), 8)
            frame[:] = cv2.add(frame, cv2.addWeighted(layer, 0.85, glow, 0.8, 0))


def mouth_geometry(face_result, hand_result, width, height):
    """Return mouth position, head direction, face size, and fingertip proximity."""
    if not face_result.face_landmarks or not face_result.facial_transformation_matrixes:
        return None, None, 0, False
    face = face_result.face_landmarks[0]
    mouth = ((face[13].x + face[14].x) * width / 2,
             (face[13].y + face[14].y) * height / 2)
    face_width = (max(p.x for p in face) - min(p.x for p in face)) * width
    radius = max(12, face_width * 0.22)
    near = any(math.dist((hand[i].x * width, hand[i].y * height), mouth) <= radius
               for hand in hand_result.hand_landmarks for i in (8, 12))
    forward = head_rotation(face_result.facial_transformation_matrixes[0])[:, 2]
    return mouth, forward, face_width, near
