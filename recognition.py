import math
import json
from pathlib import Path
SIGNS = ("dragon", "tiger", "dog", "rat", "ram", "horse", "monkey", "bird", "ox", "serpent", "hare", "boar")
DATA_PATH = Path(__file__).resolve().parent / "assets" / "hand_signs.json"


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


class RecordedMatcher:
    """Cache normalized samples and compare batches for dense calibration data."""
    def __init__(self, samples):
        import numpy as np
        self.np = np
        self.samples = samples
        self.revision = None
        self.groups = {}

    def recognize(self, pose, threshold=0.35, allowed_signs=None):
        selected = tuple(sign for sign in SIGNS if allowed_signs is None or sign in allowed_signs)
        revision = tuple((sign, id(self.samples[sign])) for sign in selected)
        if revision != self.revision:
            groups = {}
            for sign in selected:
                for sample in self.samples[sign]:
                    features = pose_features(sample)
                    if features is not None:
                        labels = tuple(h['handedness'] for h in sample['hands'])
                        groups.setdefault(labels, []).append((sign, features))
            self.groups = {labels: ([row[0] for row in rows], self.np.asarray([row[1] for row in rows]))
                           for labels, rows in groups.items()}
            self.revision = revision
        features = pose_features(pose)
        if features is None:
            return 'No hands', None
        group = self.groups.get(tuple(h['handedness'] for h in pose['hands']))
        if group is None:
            return 'Unknown', None
        names, references = group
        distances = self.np.sqrt(self.np.mean((references - features) ** 2, axis=1))
        index = int(distances.argmin())
        distance = float(distances[index])
        return (names[index] if distance <= threshold else 'Unknown'), distance

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
