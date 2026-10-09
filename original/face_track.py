"""Webcam face landmarks and approximate head orientation (not eye gaze)."""
import argparse
import math
from pathlib import Path
import time

import cv2
import mediapipe as mp
import numpy as np
from mediapipe.tasks import python
from mediapipe.tasks.python import vision

MODEL_PATH = Path(__file__).resolve().parent / "face_landmarker.task"


def head_rotation(matrix):
    """Remove scale from the canonical-face transform to obtain a rotation."""
    u, _, vt = np.linalg.svd(np.asarray(matrix, dtype=float)[:3, :3])
    correction = np.diag([1.0, 1.0, np.linalg.det(u @ vt)])
    return u @ correction @ vt


def head_angles(rotation):
    """Return pitch, yaw, roll in degrees using Rz * Ry * Rx convention."""
    horizontal = math.hypot(rotation[0, 0], rotation[1, 0])
    yaw = math.atan2(-rotation[2, 0], horizontal)
    if horizontal > 1e-6:
        pitch = math.atan2(rotation[2, 1], rotation[2, 2])
        roll = math.atan2(rotation[1, 0], rotation[0, 0])
    else:
        pitch = math.atan2(-rotation[1, 2], rotation[1, 1])
        roll = 0.0
    return tuple(math.degrees(angle) for angle in (pitch, yaw, roll))


def direction_label(forward):
    """Describe projected head direction in the mirrored preview."""
    horizontal = "RIGHT" if forward[0] > 0.2 else "LEFT" if forward[0] < -0.2 else ""
    vertical = "UP" if forward[1] > 0.2 else "DOWN" if forward[1] < -0.2 else ""
    return " / ".join(part for part in (horizontal, vertical) if part) or "FORWARD"


def draw_face(frame, landmarks, rotation, show_landmarks):
    height, width = frame.shape[:2]
    points = [(int(p.x * width), int(p.y * height)) for p in landmarks]
    if show_landmarks:
        for point in points:
            cv2.circle(frame, point, 1, (250, 180, 200), -1)
    xs, ys = zip(*points)
    cv2.rectangle(frame, (min(xs), min(ys)), (max(xs), max(ys)), (255, 255, 0), 1)
    origin = points[1]  # Nose landmark.
    forward = rotation[:, 2]  # Canonical face +Z points out of the face.
    length = max(40, int((max(xs) - min(xs)) * 0.8))
    endpoint = (int(origin[0] + forward[0] * length),
                int(origin[1] - forward[1] * length))
    if math.dist(origin, endpoint) > 3:
        cv2.arrowedLine(frame, origin, endpoint, (0, 210, 255), 3, tipLength=0.25)
    else:
        cv2.circle(frame, origin, 6, (0, 210, 255), 2)
    pitch, yaw, roll = head_angles(rotation)
    return [f"Head direction: {direction_label(forward)}",
            f"Pitch {pitch:+.1f}  Yaw {yaw:+.1f}  Roll {roll:+.1f}"]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--camera", type=int, default=0, help="Webcam index (default: 0).")
    parser.add_argument("--model", type=Path, default=MODEL_PATH, help="Face landmarker model path.")
    parser.add_argument("--landmarks", action="store_true", help="Show face landmark dots.")
    args = parser.parse_args(argv)
    if not args.model.is_file():
        parser.error(f"Model missing: {args.model}. Download face_landmarker.task as described in README.md.")
    options = vision.FaceLandmarkerOptions(
        base_options=python.BaseOptions(model_asset_path=str(args.model.resolve())),
        running_mode=vision.RunningMode.VIDEO,
        num_faces=1,
        output_facial_transformation_matrixes=True,
    )
    cap = cv2.VideoCapture(args.camera)
    try:
        if not cap.isOpened():
            raise RuntimeError(f"Could not open webcam {args.camera}")
        with vision.FaceLandmarker.create_from_options(options) as landmarker:
            started = time.monotonic()
            timestamp_ms = -1
            while True:
                success, frame = cap.read()
                if not success:
                    raise RuntimeError("Could not read a frame from the webcam")
                frame = cv2.flip(frame, 1)
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                timestamp_ms = max(timestamp_ms + 1, int((time.monotonic() - started) * 1000))
                result = landmarker.detect_for_video(
                    mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb), timestamp_ms)
                lines = ["No face detected"]
                if result.face_landmarks and result.facial_transformation_matrixes:
                    rotation = head_rotation(result.facial_transformation_matrixes[0])
                    lines = draw_face(frame, result.face_landmarks[0], rotation, args.landmarks)
                for index, line in enumerate(lines + ["Head orientation, not eye gaze | Q / Esc to quit"]):
                    position = (10, 28 + index * 28)
                    cv2.putText(frame, line, position, cv2.FONT_HERSHEY_SIMPLEX,
                                0.6, (0, 0, 0), 4, cv2.LINE_AA)
                    cv2.putText(frame, line, position, cv2.FONT_HERSHEY_SIMPLEX,
                                0.6, (255, 255, 255), 1, cv2.LINE_AA)
                cv2.imshow("Face and Head Tracking", frame)
                if cv2.waitKey(1) & 0xFF in (ord("q"), 27):
                    break
                if cv2.getWindowProperty("Face and Head Tracking", cv2.WND_PROP_VISIBLE) < 1:
                    break
    finally:
        cap.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
