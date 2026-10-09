# Hand Track

A webcam hand-tracking demo built with OpenCV and MediaPipe. The application
detects up to two hands, draws their landmarks and skeleton connections, and
can optionally label each fingertip.

## Requirements

- Python 3
- A working webcam
- OpenCV
- MediaPipe
- The MediaPipe hand-landmarker model file:
  `hand_landmarker.task`

The model file must be in the same directory as `main.py`.

## Installation

Create and activate a virtual environment, then install the dependencies:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install opencv-python mediapipe
```

## Running the application

Start hand tracking normally:

```powershell
python main.py
```

Press `q` while the video window is focused to stop the application.

### Show fingertip names

Fingertip identifiers are hidden by default. Pass `--fingers` to display the
name next to each detected fingertip:

```powershell
python main.py --fingers
```

The available identifiers are:

- `Thumb`
- `Index`
- `Middle`
- `Ring`
- `Pinky`

## How it works

1. OpenCV captures frames from the default webcam.
2. Each frame is flipped horizontally to behave like a mirror.
3. The frame is converted from BGR to RGB for MediaPipe.
4. MediaPipe's Hand Landmarker detects up to two hands in video mode.
5. Normalized landmark coordinates are converted to pixel coordinates.
6. OpenCV draws the hand skeleton and cyan landmark dots.
7. If `--fingers` is supplied, fingertip names are drawn next to the
   corresponding fingertip.

### Hand landmark indices

MediaPipe returns 21 landmarks for each hand:

| Landmark | Indices |
| --- | --- |
| Wrist | `0` |
| Thumb | `1-4` |
| Index finger | `5-8` |
| Middle finger | `9-12` |
| Ring finger | `13-16` |
| Pinky | `17-20` |

The fingertip indices used for labels are:

| Finger | Fingertip index |
| --- | --- |
| Thumb | `4` |
| Index | `8` |
| Middle | `12` |
| Ring | `16` |
| Pinky | `20` |

### Landmark reference

The following reference shows the MediaPipe hand landmark numbering used by
the classifier:

![MediaPipe hand landmark reference](landmark-reference.png)

## Naruto hand signs

The default mode shows only the hand skeleton and landmarks. To record a sign:

```powershell
python main.py --record-dragon
```

Hold the sign with both hands. A visible **5-second countdown** starts when
the camera preview opens, then saves automatically every 5 seconds. Each save
requires two detected hands; otherwise that sample is skipped and the timer
restarts. Hold the pose for several samples, then press **q** to quit.
Samples append to previous recordings. Overlapping fingers can make detection
less reliable, so check that both hand skeletons are visible.

Available recording flags: `--record-dragon`, `--record-tiger`, `--record-dog`,
`--record-rat`, `--record-ram`, `--record-horse`, `--record-monkey`,
`--record-bird`, `--record-ox`, `--record-serpent`, `--record-hare`,
and `--record-boar`.

Samples append to `hand_signs.json` beside `main.py`. Each sample stores all 21
normalized XYZ landmarks and handedness for each visible hand. Existing
samples are preserved between sessions.

Recognize your recorded signs:

```powershell
python main.py --naruto
```

Naruto mode hides the skeleton lines and landmark dots, keeping the recognized
sign visible.

Recognition compares live
poses to your recorded examples after removing translation and scale, while
preserving relative hand placement. Unmatched poses display `Unknown`.
This is a simple sample matcher; record more examples to improve coverage.
It does not include pretrained Naruto signs; effects use your recorded samples
Choose one mode per invocation. `--fingers` works with any mode.

## Claw, fist, and rest detection (`--circle`)

In circle mode, the application classifies each detected hand as `CLAW`, `FIST`, or `REST`. The
result is displayed near that hand's wrist.
Claw indicators are orange and fist indicators are red.
Relaxed-hand indicators are gray.

### Detection signals

The classifier first compares the four non-thumb fingertips (`8`, `12`, `16`,
and `20`) with the wrist (`0`).

- If all four fingertips are very close to the wrist, the result is
  `FIST`.
- Otherwise, the classifier checks whether the PIP/second knuckles are bent:
  `6` for index, `10` for middle, `14` for ring, and `18` for pinky.
- If at least two of those knuckles are bent, the result is `CLAW`.
- If fewer than two are bent, the result is `REST`.

Distances are normalized using the wrist-to-middle-finger-base measurement,
and knuckle angles are used for the bend check. This makes the result less
sensitive to how close the hand is to the camera.

The current implementation uses normalized fingertip-to-wrist distance and
second-knuckle angles in `classify_hand(points)`. The `1.0` fist threshold and
the `155` degree knuckle-bend threshold may need calibration for different
cameras, lighting, and hand positions. A short temporal smoothing window could
also prevent the result from flickering when the hand is between poses.

## Claw portal effect

When both hands are detected as claws, the application checks their handedness
and screen positions:

- The right hand must be on the left side of the screen.
- The left hand must be on the right side of the screen.
- Bring the fingertip groups within `1.8` average palm lengths to start
  the circle. Two claws appearing far apart do not activate it.

When the circle first appears, a halo of glowing sparkles gathers inward
toward the ring and fades over 0.55 seconds. Adjust
`PORTAL_CREATION_DURATION` and `PORTAL_CREATION_SPARKLE_COUNT` in `main.py`
to tune this creation effect.

Once activated, a glowing portal ring stays open as the claws pull apart.
Its center is the midpoint between the two fingertip groups, and its radius
grows with their separation. Releasing either claw, losing hand detection,
or reversing the required screen positions resets the portal; bring the
claws close again to restart it. On release, the last ring breaks into glowing
sparkles that drift outward, twinkle, and fade away. Adjust
`PORTAL_SPARKLE_DURATION` (seconds) and `PORTAL_SPARKLE_COUNT` near the top of
`main.py` to tune the effect.

Adjust `PORTAL_START_DISTANCE = 1.8` near the top of `main.py` to change the
activation distance in average palm lengths. Use a positive value; smaller
values require the claws to come closer before the circle starts.
Run the original effect with `python main.py --circle`.

## Project files

- `main.py` - webcam capture, MediaPipe hand tracking, skeleton rendering,
  landmark dots, optional fingertip labels, claw/fist/rest classification, and
  the claw portal effect.
- `hand_landmarker.task` - MediaPipe hand-landmark model used at runtime.
- `landmark-reference.png` - MediaPipe landmark numbering reference image.
- `README.md` - setup and usage documentation.

## Face and head tracking

Run the separate MediaPipe Face Landmarker webcam script:

```powershell
python face_track.py
python face_track.py --landmarks
python face_track.py --camera 1
```

It shows a face bounding box, an approximate head-direction arrow, and pitch,
yaw, and roll in degrees. Left/right/up/down labels refer to the mirrored
preview. Use `--landmarks` to show face landmark dots. Press **q** or **Esc**
to exit. Close the hand-tracking app first so it releases the webcam.

This estimates head orientation, not eye gaze or the point you are looking at
on your screen. Angles use the model's canonical face orientation as their
reference and are approximate rather than calibrated physical measurements.

The script uses the existing OpenCV and MediaPipe dependencies, plus NumPy
(installed with them). Keep `face_landmarker.task` beside `face_track.py`, or
pass `--model PATH`. To download the model again:

```powershell
Invoke-WebRequest -Uri "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/latest/face_landmarker.task" -OutFile face_landmarker.task
```

Implementation reference: [Google's Python Face Landmarker guide](https://developers.google.com/edge/mediapipe/solutions/vision/face_landmarker/python).

## Fireball Jutsu (`--naruto`)

Record the six required signs, then run `python main.py --naruto`:

**Snake (serpent) ? ram ? monkey ? boar ? horse ? tiger**.

Snake uses `--record-serpent`. Hold each sign for at least 0.3 seconds so it
counts. The preview shows sequence progress and the next sign. A different
recognized sign out of order resets progress; holding the last accepted sign
does not count twice. Unknown poses during transitions are ignored. Progress
expires after 12 seconds without another accepted sign.

After tiger, bring your index or middle fingertips near your mouth and keep
them there for **0.3 continuous seconds**. Face Landmarker finds the mouth;
leaving the mouth area or losing face/hand tracking restarts that hold.
A fast, narrow procedural flame jet emits from your mouth for three seconds,
then the sequence resets so you can cast again. No face or hand skeleton is
shown in Naruto mode. Missing required recordings are listed in the preview.

The flame direction follows the estimated head direction in the camera view.
When facing directly toward the camera, the fire expands toward the viewer
in the 2D preview. Turning or tilting your head aims the stream sideways or
vertically using the same head rotation as `face_track.py`. This is a webcam overlay, not a physical simulation.
`face_landmarker.task` is required beside the scripts. Timing constants and
the flame renderer are in `jutsu.py`.
