# signs

A local four-lane hand gesture rhythm game built from your `hand-track` recordings and recognition logic. Black playfield, falling notes, colored hit circles, score, accuracy, and pause controls follow the supplied reference.

## Run

Double-click **Signs.exe** in this folder to open the game in its own desktop window. The application starts its local hand-tracking and music services internally; closing the game stops those services. If a browser server is already running, the desktop app reuses it and leaves it running on exit. Keep the executable beside `desktop.py`, `server.py`, and `.venv`. Startup errors are logged in `logs/launcher.log`. The window uses pywebview and the installed Microsoft WebView2 runtime. Desktop settings persist in `.desktop-profile`; your songs, maps, and calibration stay in the existing project folders.

To rebuild the executable after editing `tools/GameLauncher.cs`, run `powershell -ExecutionPolicy Bypass -File .\tools\build_launcher.ps1`.

For the browser version, run from this directory in PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File .\launch.ps1
```

Open http://127.0.0.1:8765 if the browser opens before the server is ready. The launcher uses this project's `.venv` when present. MP3 import requires the dependencies in `requirements.txt`. For independent installation:

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python server.py
```

Choose **Hands** to start the webcam. Keyboard mode uses **D F J K**, and clicking/tapping lanes also works. **Esc** pauses/resumes, **R** restarts, **Q** returns to the menu. Closing the server with Ctrl+C releases the camera. Choose Keyboard to stop camera tracking.

## Calibration

Click **Calibrate** beside **Sign library** to browse and record any of the twelve signs. Use the left/right arrows, keyboard arrow keys, or swipe the pose area. Navigation wraps between the first and last signs and pauses during recording. Browsing does not change saved recordings. For each sign, prepare the shown pose and click **Start 15-second recording**. This immediately clears that sign's old game recordings. Slowly move the pose up and down, rotate left and right, and tilt toward and away from the camera while keeping both hands visible and the finger positions intact.

Every processed frame with both left and right hands detected is captured, without requiring the old classifier to recognize your pose. The timer runs for 15 seconds even if tracking is lost. A live count shows accepted samples. Record again if none were captured; otherwise advance to the next sign. Closing during a recording saves the partial replacement. Other signs are preserved. Changes persist to `assets/hand_signs.json` and recognition updates immediately. The original project in `hand-track` is untouched; `assets/sign_reference.json` preserves pose drawings for guidance after recordings are cleared. The guided calibration menu supports all twelve signs.

## Recorded data

`assets/hand_signs.json` contains all 88 original samples across dragon, tiger, dog, rat, ram, horse, monkey, bird, ox, serpent, hare, and boar. `recognition.py` preserves the original sample validation, handedness matching, palm-size normalization, relative hand placement, RMS distance threshold (0.35), and claw/fist/rest classifier. `assets/hand_landmarker.task` is the original two-hand MediaPipe model. The camera is mirrored before detection, as in the source project.

The sign library and next-sign panel render actual recorded skeletons. Keep both hands visible and use similar orientations to your recordings. Recognition is a sample matcher, so occluded or substantially rotated poses may remain Unknown. The game adds an 80 ms recognition hold. Repeated identical signs require a release or different pose between hits; holding one sign cannot automatically hit repeated notes.

The five 60-second demo tracks are original synthesized beats at 90-120 BPM, with single-pose tap and hold notes. The difficulty slider selects 3-5 signs for the next run, using the first slots of your Signs wheel. The default five are serpent, tiger, monkey, hare, and dragon. Every level includes the signs from the previous level. Changes while paused apply on restart. There are no simultaneous chords because one pair of hands performs one sign at a time. Perfect hits are within 100 ms; good hits within 230 ms. Pause freezes the chart and stops audio; resume continues at the same position.

`original/` preserves the original hand tracker, face tracker, jutsu sequence/effect logic, and documentation for reference. Face/fireball and portal effects are not active in the rhythm game. The demo tracks are synthesized originals; imported MP3s play their own audio.

The server listens only on localhost. Webcam processing stays in Python on this computer; the browser polls local recognition and a mirrored preview. The camera starts only after selecting Hands.

Recognition compares only against the signs enabled by the difficulty selection. At level 3 it searches the first three wheel slots; level 4 adds the fourth slot and level 5 adds the fifth. Disabled signs are excluded from the matcher, and distant poses remain Unknown. During a run (including pause), the tracker keeps that run's sign selection until restart. Calibration still captures raw two-hand poses independently of difficulty.

Hold notes have a thin colored tail above their bar. Hit the head on the beat and hold the sign, keyboard key, or lane touch until the tail reaches the hit line. Durations are one or two beats at the selected track's tempo, and the next sign starts on the following beat. Early release breaks the hold. Webcam holds allow 180 ms of recognition flicker and reject stale tracking after 250 ms. Completed holds award 500 bonus points per held beat; broken holds count as misses. Pause freezes the hold timer; losing window focus pauses play.

The start screen opens a shuffled five-track list before difficulty selection. Choose Midnight Circuit (100 BPM), Violet Static (112), Teal Undertow (90), Afterglow (120), or Shadow Orbit (108), or use Surprise me for a random selection. Each track has its own synth palette, chord/melody pattern, and note pattern. Tap and hold timing follows the selected tempo. Back controls return to track selection or the start screen. These are synthesized original tracks, not imported commercial recordings.

## Import MP3 songs

Choose **Start**, then **Import MP3** on the track list. Select a local `.mp3` (up to 100 MB and 20 minutes). The server decodes the audio and runs librosa's onset-strength and beat-tracking algorithms in the background. The status displays upload/analysis progress; the first analysis may take longer while libraries initialize. Once **Beatmap saved** appears, select the new song, choose 3-5 signs, and play. Track pages keep the list compact as your library grows.

MP3s live under `songs/`. A `<filename>.mp3.beats.json` file stores each beatmap. Browser uploads use generated IDs for their filenames; files dropped into the folder keep their names. The JSON includes the display title, duration, estimated BPM, and actual beat timestamps in seconds. Tracks reload automatically after server restart. Silent, invalid, very short, or rhythm-free files report an error instead of creating an unusable map.

Imported songs get a three-second lead-in before audio playback. Notes follow every detected beat. Beats within a hold are covered by that held sign; the next sign lands on the beat immediately after the hold ends. Hold tails end on later detected beats, so local beat spacing determines the duration. Difficulty changes select different signs without reanalyzing the MP3. The game clock follows the song's actual playback time; pause/resume preserves that position and restart returns to the beginning. Imported songs play at their original length, without the synthesized backing beat. Volume applies to both kinds of track.

Beat detection is an estimate and can identify half/double tempo or miss beats in some songs. This version generates a playable map automatically; use the Map editor to adjust the generated timing manually.

Checks:

```powershell
.venv\Scripts\python -m unittest discover -s tests
node tests/test_charts.mjs
```

## Songs folder and automatic analysis

Put an MP3 directly into `songs/` while the server is running, or before launching it. The watcher checks every two seconds, waits for the file size and modification time to settle, and analyzes each new or changed file in the background. Once ready, the song appears automatically in the track list, with its BPM and beatmap. Matching cached beatmaps are reused after restart. Invalid files report an error and remain in the folder; changing the file or restarting the server allows a retry. The track list shows analysis status and refreshes automatically. Folder discovery covers MP3 files directly in `songs/` (not nested subfolders).

All five demos now have MP3 files in `songs/`, with BPMs in their filenames. `songs/catalog.json` stores their original titles, tempos, and synth settings; `tracks.js` reads that catalog. To recreate missing demo audio, run `.venv\Scripts\python tools/create_demo_songs.py`. This keeps existing audio files intact.

## Choose your five signs

Click **Signs** beside **Sign library**. The wheel has five slots, and each can use any of the twelve calibrated signs. Click a slot, then a sign below to replace it. Choosing a sign already in another slot swaps those slots, keeping all five unique. Difficulty uses the first 3, 4, or 5 slots; dimmed slots are outside the current difficulty. Your selection is remembered in this browser. Changing it during a match pauses play and applies to the next match or restart; the current chart and tracker keep their original selection. Calibration and the reference library still include all twelve signs.

## Map editor

Click **Map editor** just left of **Signs** in the header. This opens a full-screen editor. Select an analyzed song or use **Import MP3** inside the editor. You can begin with its auto-generated notes, use **Generate from beats**, or start a **New empty map**.

- Drag a sign from the five-slot palette onto a lane to add a note. **+ Tap** and **+ Hold** let you click empty space to place those note types.
- In **Move** mode, drag a note bar to change its time and lane. Drag the square at the end of its skinny line to change a hold's end time.
- Choose **1/4 beat**, **1/8 beat**, **1/16 beat**, or **Free** snapping. Fractions divide each detected beat, interpolating between its timestamps; they are not fractions of a measure.
- Use the selected-note inspector to adjust its sign slot, lane, start time, and hold length. Right-click or press Delete to remove a selected note. Undo/redo is available, including Ctrl+Z and Ctrl+Shift+Z.
- Preview the song, scroll over the timeline or use its position slider, and adjust zoom. Follow keeps the playing section in view.
- Name the map and click **Save map**. One custom map per song is saved under `songs/maps/<track-id>.json`; the track list marks it as **CUSTOM MAP**, and matches use its note positions and tails. Saving again updates that song's custom map.

Notes store sign-slot numbers. They follow the current Signs wheel when playing; difficulty maps them to the first 3, 4, or 5 active slots. The song beatmap and MP3 are preserved when saving a custom map. Unsaved edits are kept as browser-local drafts, including when switching songs or leaving the editor.

Additional editor checks: `node tests/test_editor.mjs`.
