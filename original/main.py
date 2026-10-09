import argparse
from contextlib import ExitStack
import math
import json
from pathlib import Path
import random
import time

import cv2
import mediapipe as mp

from mediapipe.tasks import python
from mediapipe.tasks.python import vision

from jutsu import FireballJutsu, mouth_geometry
from face_track import MODEL_PATH as FACE_MODEL_PATH

SIGNS = ("dragon", "tiger", "dog", "rat", "ram", "horse", "monkey",
         "bird", "ox", "serpent", "hare", "boar")
RECORD_INTERVAL = 5.0
DATA_PATH = Path(__file__).resolve().parent / "hand_signs.json"


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Capture hands, record signs, or run effects.")
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--circle", action="store_true", help="Run the claw circle effect.")
    modes.add_argument("--naruto", dest="naruto", action="store_true",
                       help="Recognize recorded Naruto hand signs.")
    for sign in SIGNS:
        modes.add_argument(f"--record-{sign}", dest="record_sign",
                           action="store_const", const=sign,
                           help=f"Record {sign} poses automatically every 5 seconds.")
    parser.add_argument("--fingers", action="store_true", help="Label fingertips.")
    return parser.parse_args(argv)


def load_signs(path=DATA_PATH):
    if not path.exists():
        return {sign: [] for sign in SIGNS}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("version") != 1:
            raise ValueError("Unsupported recording format")
        samples = data["signs"]
        for sign in SIGNS:
            samples.setdefault(sign, [])
            for sample in samples[sign]:
                hands = sample["hands"]
                if not 1 <= len(hands) <= 2:
                    raise ValueError("Invalid hand count")
                for hand in hands:
                    if hand["handedness"] not in ("left", "right") or len(hand["landmarks"]) != 21:
                        raise ValueError("Invalid hand sample")
                    if any(len(point) != 3 or any(not math.isfinite(v) for v in point)
                           for point in hand["landmarks"]):
                        raise ValueError("Invalid landmarks")
        return samples
    except (ValueError, TypeError, KeyError, AttributeError) as error:
        raise ValueError(f"Invalid recordings in {path}: {error}") from error


def capture_pose(result):
    """Keep normalized XYZ landmarks and handedness for every visible hand."""
    return {"hands": sorted([
        {"handedness": result.handedness[i][0].category_name.lower(),
         "landmarks": [[p.x, p.y, p.z] for p in hand]}
        for i, hand in enumerate(result.hand_landmarks)
    ], key=lambda hand: hand["handedness"])}


def record_sign(sign, pose, samples, path=DATA_PATH):
    """Append one labeled pose and atomically persist all recordings."""
    if sign not in SIGNS or not pose["hands"]:
        return False
    updated = {name: list(rows) for name, rows in samples.items()}
    updated[sign].append(pose)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps({"version": 1, "signs": updated}, indent=2),
                         encoding="utf-8")
    temporary.replace(path)
    samples[sign] = updated[sign]
    return True


def pose_features(pose):
    """Remove camera translation and scale, preserving relative hand placement."""
    hands = pose["hands"]
    if not hands:
        return None
    scale = sum(math.dist(h["landmarks"][0], h["landmarks"][9]) for h in hands) / len(hands)
    if scale < 1e-6:
        return None
    origin = [sum(h["landmarks"][0][i] for h in hands) / len(hands) for i in range(2)]
    values = []
    for hand in hands:
        wrist = hand["landmarks"][0]
        for point in hand["landmarks"]:
            values.extend(((point[0] - origin[0]) / scale,
                           (point[1] - origin[1]) / scale,
                           (point[2] - wrist[2]) / scale))
    return values


def recognize_sign(pose, samples, threshold=0.35):
    """Find the closest recorded pose; reject distant or mismatched hands."""
    features = pose_features(pose)
    if features is None:
        return "No hands", None
    labels = [h["handedness"] for h in pose["hands"]]
    best_sign, best_distance = "Unknown", float("inf")
    for sign in SIGNS:
        for sample in samples[sign]:
            if [h["handedness"] for h in sample["hands"]] != labels:
                continue
            reference = pose_features(sample)
            if reference is None:
                continue
            distance = math.sqrt(sum((a - b) ** 2 for a, b in zip(features, reference)) / len(features))
            if distance < best_distance:
                best_sign, best_distance = sign, distance
    return (best_sign if best_distance <= threshold else "Unknown"), best_distance


# Maximum fingertip separation in average palm lengths to start the circle.
# Lower this value to require the claws to come closer together.
PORTAL_START_DISTANCE = 1.8
# Release effect settings: duration in seconds and number of sparkles.
PORTAL_SPARKLE_DURATION = 0.8
PORTAL_SPARKLE_COUNT = 70
PORTAL_CREATION_DURATION = 0.55
PORTAL_CREATION_SPARKLE_COUNT = 50
if not math.isfinite(PORTAL_START_DISTANCE) or PORTAL_START_DISTANCE <= 0:
    raise ValueError("PORTAL_START_DISTANCE must be a positive finite number")

# Initialize MediaPipe Hand Landmarker
base_options = python.BaseOptions(
    model_asset_path=str(Path(__file__).resolve().parent / "hand_landmarker.task"),
)

options = vision.HandLandmarkerOptions(
    base_options=base_options,
    running_mode=vision.RunningMode.VIDEO,
    num_hands=2,
)

# Colors in OpenCV use BGR (Blue, Green, Red)
LAVENDER = (250, 180, 200)
CYAN = (255, 255, 0)
CLAW_COLOR = (0, 165, 255)
FIST_COLOR = (0, 0, 255)
REST_COLOR = (128, 128, 128)

# MediaPipe fingertip landmark indices
FINGERTIP_NAMES = {
    4: "Thumb",
    8: "Index",
    12: "Middle",
    16: "Ring",
    20: "Pinky",
}

# Hand skeleton connections
HAND_CONNECTIONS = [
    (0, 1),
    (1, 2),
    (2, 3),
    (3, 4),  # Thumb
    (0, 5),
    (5, 6),
    (6, 7),
    (7, 8),  # Index
    (5, 9),
    (9, 10),
    (10, 11),
    (11, 12),  # Middle
    (9, 13),
    (13, 14),
    (14, 15),
    (15, 16),  # Ring
    (13, 17),
    (17, 18),
    (18, 19),
    (19, 20),  # Pinky
    (0, 17),  # Palm
]


def joint_angle(first, middle, last):
    """Return the angle at the middle point in degrees."""
    first_vector = (
        first[0] - middle[0],
        first[1] - middle[1],
    )
    last_vector = (
        last[0] - middle[0],
        last[1] - middle[1],
    )
    first_length = math.hypot(*first_vector)
    last_length = math.hypot(*last_vector)

    if first_length == 0 or last_length == 0:
        return 180.0

    cosine = (
        (first_vector[0] * last_vector[0])
        + (first_vector[1] * last_vector[1])
    ) / (first_length * last_length)
    return math.degrees(math.acos(max(-1.0, min(1.0, cosine))))


def classify_hand(points):
    """Classify a hand as a claw, fist, or relaxed."""
    palm_size = math.dist(points[0], points[9])
    if palm_size == 0:
        return "REST"

    fingertip_distances = [
        math.dist(points[fingertip], points[0]) / palm_size
        for fingertip in (8, 12, 16, 20)
    ]

    # A fist brings every fingertip very close to the wrist.
    if max(fingertip_distances) < 1.0:
        return "FIST"

    finger_chains = (
        (5, 6, 7),
        (9, 10, 11),
        (13, 14, 15),
        (17, 18, 19),
    )
    bent_knuckles = sum(
        joint_angle(points[mcp], points[pip], points[dip]) < 155
        for mcp, pip, dip in finger_chains
    )

    # A claw has multiple bent PIP/second knuckles. Otherwise the hand is
    # relaxed, even if its fingertips are not fully extended.
    if bent_knuckles >= 2:
        return "CLAW"

    return "REST"


def fingertip_center(points):
    """Return the center of the four non-thumb fingertips."""
    fingertips = [points[index] for index in (8, 12, 16, 20)]
    return (
        sum(point[0] for point in fingertips) // len(fingertips),
        sum(point[1] for point in fingertips) // len(fingertips),
    )


def update_portal_active(active, left_hand, right_hand, start_distance):
    """Require nearby claws to activate; reset when a claw or its position is lost."""
    if left_hand is None or right_hand is None:
        return False

    left_center = fingertip_center(left_hand)
    right_center = fingertip_center(right_hand)
    if right_center[0] >= left_center[0]:
        return False

    palm_size = (
        math.dist(left_hand[0], left_hand[9])
        + math.dist(right_hand[0], right_hand[9])
    ) / 2
    if palm_size <= 0:
        return False

    return active or math.dist(left_center, right_center) <= palm_size * start_distance


def draw_portal(frame, left_hand, right_hand):
    """Draw the activated portal, growing as the claws move apart."""
    left_fingertips = fingertip_center(left_hand)
    right_fingertips = fingertip_center(right_hand)
    separation = math.dist(left_fingertips, right_fingertips)
    center = (
        (left_fingertips[0] + right_fingertips[0]) // 2,
        (left_fingertips[1] + right_fingertips[1]) // 2,
    )
    radius = max(20, int(separation * 0.45))
    glow = frame.copy()
    glow[:] = 0

    cv2.circle(glow, center, radius, (255, 80, 220), 10)
    cv2.circle(glow, center, max(2, radius - 12), (255, 180, 255), 3)
    cv2.circle(glow, center, max(2, radius // 3), (180, 60, 255), 2)
    glow = cv2.GaussianBlur(glow, (0, 0), 12)
    frame[:] = cv2.addWeighted(frame, 0.7, glow, 0.3, 0)

    cv2.circle(frame, center, radius, (255, 120, 240), 3)
    cv2.circle(frame, center, max(2, radius - 12), (255, 220, 255), 1)

    return center, radius


def create_release_sparkles(center, radius, now):
    """Scatter particles around the last visible ring."""
    particles = []
    for _ in range(PORTAL_SPARKLE_COUNT):
        angle = random.uniform(0, math.tau)
        distance = radius + random.uniform(-5, 5)
        speed = random.uniform(35, 130)
        particles.append({
            "x": center[0] + math.cos(angle) * distance,
            "y": center[1] + math.sin(angle) * distance,
            "vx": math.cos(angle) * speed,
            "vy": math.sin(angle) * speed - 25,
            "born": now,
            "life": PORTAL_SPARKLE_DURATION * random.uniform(0.6, 1.0),
            "size": random.randint(2, 4),
            "phase": random.uniform(0, math.tau),
        })
    return particles



def create_formation_sparkles(center, radius, now):
    """Gather a halo of sparkles inward toward the newly created ring."""
    particles = []
    for _ in range(PORTAL_CREATION_SPARKLE_COUNT):
        angle = random.uniform(0, math.tau)
        life = PORTAL_CREATION_DURATION * random.uniform(0.75, 1.0)
        travel = random.uniform(25, 65)
        distance = radius + travel
        particles.append({
            "x": center[0] + math.cos(angle) * distance,
            "y": center[1] + math.sin(angle) * distance,
            "vx": -math.cos(angle) * travel / life,
            "vy": -math.sin(angle) * travel / life,
            "born": now,
            "life": life,
            "size": random.randint(2, 4),
            "phase": random.uniform(0, math.tau),
            "gravity": 0,
        })
    return particles


def draw_release_sparkles(frame, particles, now):
    """Draw twinkling creation or release sparkles until they fade."""
    particles[:] = [p for p in particles if now - p["born"] < p["life"]]
    if not particles:
        return
    layer = frame.copy()
    layer[:] = 0
    for p in particles:
        age = max(0.0, now - p["born"])
        fade = (1.0 - age / p["life"]) ** 2
        twinkle = 0.65 + 0.35 * math.sin(age * 30 + p["phase"])
        color = tuple(int(c * fade * twinkle) for c in (255, 210, 255))
        x = int(p["x"] + p["vx"] * age)
        y = int(p["y"] + p["vy"] * age + p.get("gravity", 45) * age * age)
        size = max(1, int(p["size"] * (1.0 - age / p["life"])))
        cv2.circle(layer, (x, y), size, color, -1, cv2.LINE_AA)
        cv2.line(layer, (x - size * 2, y), (x + size * 2, y), color, 1, cv2.LINE_AA)
        cv2.line(layer, (x, y - size * 2), (x, y + size * 2), color, 1, cv2.LINE_AA)
    glow = cv2.GaussianBlur(layer, (0, 0), 4)
    frame[:] = cv2.add(frame, cv2.addWeighted(layer, 1.0, glow, 0.6, 0))


def main(argv=None):
    args = parse_args(argv)
    samples = load_signs() if args.naruto or args.record_sign else {}
    status = ""
    status_until = 0
    next_record_at = None
    if args.naruto and not FACE_MODEL_PATH.is_file():
        raise FileNotFoundError(f"Fireball mode needs the face model: {FACE_MODEL_PATH}")
    jutsu = FireballJutsu() if args.naruto else None
    cap = cv2.VideoCapture(0)

    if not cap.isOpened():
        raise RuntimeError("Could not open webcam")

    try:
        with ExitStack() as stack:
            landmarker = stack.enter_context(vision.HandLandmarker.create_from_options(options))
            face_landmarker = None
            if args.naruto:
                face_options = vision.FaceLandmarkerOptions(
                    base_options=python.BaseOptions(model_asset_path=str(FACE_MODEL_PATH)),
                    running_mode=vision.RunningMode.VIDEO, num_faces=1,
                    output_facial_transformation_matrixes=True,
                )
                face_landmarker = stack.enter_context(vision.FaceLandmarker.create_from_options(face_options))
            timestamp_ms = -1
            started = time.monotonic()
            portal_active = False
            last_portal = None
            release_sparkles = []
            formation_sparkles = []

            while True:
                success, frame = cap.read()

                if not success:
                    break

                frame = cv2.flip(frame, 1)
                height, width, _ = frame.shape

                # Convert BGR to RGB
                rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

                mp_image = mp.Image(
                    image_format=mp.ImageFormat.SRGB,
                    data=rgb_frame,
                )

                timestamp_ms = max(timestamp_ms + 1, int((time.monotonic() - started) * 1000))

                # Detect hand landmarks
                result = landmarker.detect_for_video(mp_image, timestamp_ms)

                claw_hands = {}
                for hand_index, hand in enumerate(result.hand_landmarks):
                    points = []

                    # Convert normalized landmarks to pixel coordinates
                    for landmark in hand:
                        x = int(landmark.x * width)
                        y = int(landmark.y * height)
                        points.append((x, y))

                    if not args.naruto:
                        # Draw lavender skeleton connections
                        for start, end in HAND_CONNECTIONS:
                            cv2.line(frame, points[start], points[end], LAVENDER, 3)

                        # Draw cyan blue landmark dots
                        for point in points:
                            cv2.circle(frame, point, 5, CYAN, -1)

                    if args.circle:
                        hand_shape = classify_hand(points)
                        indicator_colors = {
                            "CLAW": CLAW_COLOR,
                            "FIST": FIST_COLOR,
                            "REST": REST_COLOR,
                        }
                        handedness = result.handedness[hand_index][0].category_name.lower()
                        if hand_shape == "CLAW":
                            claw_hands[handedness] = points

                        wrist = points[0]
                        cv2.putText(
                            frame,
                            hand_shape,
                            (wrist[0] + 10, max(30, wrist[1] - 20)),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            0.8,
                            indicator_colors[hand_shape],
                            2,
                            cv2.LINE_AA,
                        )

                    if args.fingers:
                        for fingertip_index, name in FINGERTIP_NAMES.items():
                            fingertip = points[fingertip_index]
                            cv2.putText(
                                frame,
                                name,
                                (fingertip[0] + 8, fingertip[1] - 8),
                                cv2.FONT_HERSHEY_SIMPLEX,
                                0.6,
                                LAVENDER,
                                2,
                                cv2.LINE_AA,
                            )

                if args.circle:
                    left_hand = claw_hands.get("left")
                    right_hand = claw_hands.get("right")
                    was_active = portal_active
                    now = time.monotonic()
                    portal_active = update_portal_active(
                        portal_active, left_hand, right_hand, PORTAL_START_DISTANCE
                    )
                    if was_active and not portal_active and last_portal is not None:
                        center, radius = last_portal
                        release_sparkles.extend(create_release_sparkles(center, radius, now))
                        last_portal = None
                    if portal_active:
                        last_portal = draw_portal(frame, left_hand, right_hand)
                        if not was_active:
                            center, radius = last_portal
                            formation_sparkles.extend(create_formation_sparkles(center, radius, now))
                    else:
                        formation_sparkles.clear()
                    draw_release_sparkles(frame, formation_sparkles, now)
                    draw_release_sparkles(frame, release_sparkles, now)

                pose = capture_pose(result)
                if args.record_sign:
                    now = time.monotonic()
                    if next_record_at is None:
                        next_record_at = now + RECORD_INTERVAL
                    remaining = max(0, math.ceil(next_record_at - now))
                    text = f"Record {args.record_sign}: saving in {remaining}s ({len(samples[args.record_sign])} samples)"
                    if now >= next_record_at:
                        if len(pose["hands"]) == 2:
                            record_sign(args.record_sign, pose, samples)
                            status = f"Saved {args.record_sign} ({len(samples[args.record_sign])} samples)"
                        else:
                            status = "Skipped: both hands must be detected"
                        status_until = now + 2
                        next_record_at = now + RECORD_INTERVAL
                        print(status)
                elif args.naruto:
                    sign, distance = recognize_sign(pose, samples)
                    text = f"Sign: {sign}"
                    now = time.monotonic()
                    face_result = face_landmarker.detect_for_video(mp_image, timestamp_ms)
                    mouth, forward, face_width, near_mouth = mouth_geometry(face_result, result, width, height)
                    status = jutsu.update(sign, near_mouth, now)
                    status_until = now + 1
                    missing = [name for name in ("serpent", "ram", "monkey", "boar", "horse", "tiger") if not samples[name]]
                    if missing:
                        status = "Record first: " + ", ".join(missing)
                    jutsu.draw(frame, mouth, forward, face_width, now)
                    if not any(samples.values()):
                        text = "No recordings yet: use --record-<sign> first"
                else:
                    text = "Hand capture | Q to quit"
                cv2.putText(frame, text, (10, 30), cv2.FONT_HERSHEY_SIMPLEX,
                            0.65, CYAN, 2, cv2.LINE_AA)
                if status and time.monotonic() < status_until:
                    cv2.putText(frame, status, (10, 60), cv2.FONT_HERSHEY_SIMPLEX,
                                0.6, CYAN, 2, cv2.LINE_AA)

                cv2.imshow("Hand Skeleton Tracking", frame)

                key = cv2.waitKey(1) & 0xFF
                if key == ord("q"):
                    break

    finally:
        cap.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
