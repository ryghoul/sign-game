"""Local rhythm game and webcam tracking. Camera starts only on request."""
import json
import threading
import time
import uuid
import re
from urllib.parse import urlsplit, unquote
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from recognition import SIGNS, load_signs, capture_pose, RecordedMatcher, classify_hand
from calibration import Calibration
from music import MusicLibrary, MAX_UPLOAD
from maps import save_map

ROOT = Path(__file__).resolve().parent
samples = load_signs()
calibration = Calibration(samples)
lock = threading.Lock()
state = {"status": "Camera off", "sign": "No hands", "hands": [], "shapes": []}
preview = b""
running = threading.Event()
worker = None
allowed_signs = ['serpent', 'tiger', 'monkey']
music = MusicLibrary()


def track():
    global preview
    cap = None
    try:
        import cv2
        import mediapipe as mp
        from mediapipe.tasks import python
        from mediapipe.tasks.python import vision
        matcher = RecordedMatcher(samples)
        options = vision.HandLandmarkerOptions(
            base_options=python.BaseOptions(model_asset_path=str(ROOT / 'assets/hand_landmarker.task')),
            running_mode=vision.RunningMode.VIDEO, num_hands=2)
        cap = cv2.VideoCapture(0)
        if not cap.isOpened():
            raise RuntimeError('Could not open webcam. Close other camera apps and try again.')
        with vision.HandLandmarker.create_from_options(options) as detector:
            previous = -1
            while running.is_set():
                ok, frame = cap.read()
                if not ok:
                    raise RuntimeError('Camera frame unavailable')
                frame = cv2.flip(frame, 1)
                timestamp = max(previous + 1, int(time.monotonic() * 1000))
                previous = timestamp
                result = detector.detect_for_video(mp.Image(image_format=mp.ImageFormat.SRGB,
                    data=cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)), timestamp)
                pose = capture_pose(result)
                with lock:
                    calibration.update(pose, time.monotonic())
                    sign, distance = ('Calibrating', None) if calibration.sign else matcher.recognize(pose, allowed_signs=allowed_signs)
                height, width = frame.shape[:2]
                shapes = [classify_hand([(int(p.x * width), int(p.y * height)) for p in hand])
                          for hand in result.hand_landmarks]
                _, jpg = cv2.imencode('.jpg', cv2.resize(frame, (320, 240)))
                with lock:
                    state.update(status='Tracking', sign=sign, distance=distance if distance is not None and distance != float('inf') else None,
                                 hands=pose['hands'], shapes=shapes)
                    preview = jpg.tobytes()
    except Exception as error:
        with lock:
            state.update(status=str(error), sign='No hands', hands=[], shapes=[])
    finally:
        if cap is not None:
            cap.release()
        running.clear()
        with lock:
            calibration.finish(cancelled=True)


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def log_message(self, *args):
        pass

    def json_response(self, value, status=200):
        body = json.dumps(value).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        route = urlsplit(self.path).path
        if route.startswith('/songs/') and route.lower().endswith('.mp3'):
            self.serve_song(route)
        elif route == '/api/tracks':
            self.json_response(music.tracks())
        elif route == '/api/songs/status':
            self.json_response(music.status())
        elif route.startswith('/api/imports/'):
            job = music.job(route.rsplit('/', 1)[-1])
            self.json_response(job or {'error': 'Import not found'}, 200 if job else 404)
        elif self.path.startswith('/api/state'):
            with lock:
                body = json.dumps({**state, 'allowedSigns': allowed_signs, 'calibration': calibration.snapshot(time.monotonic())}).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(body)
        elif self.path.startswith('/api/preview'):
            with lock:
                body = preview
            self.send_response(200 if body else 204)
            self.send_header('Content-Type', 'image/jpeg')
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(body)
        else:
            super().do_GET()

    def serve_song(self, route):
        name = unquote(route[len('/songs/'):])
        path = music.root / name
        if Path(name).name != name or path.resolve().parent != music.root.resolve() or not path.is_file():
            self.send_error(404)
            return
        size = path.stat().st_size
        start, end, status = 0, size - 1, 200
        requested = self.headers.get('Range')
        if requested:
            match = re.fullmatch(r'bytes=(\d*)-(\d*)', requested)
            if not match or not any(match.groups()):
                self.send_error(416)
                return
            first, last = match.groups()
            if first:
                start = int(first)
                end = min(int(last), size - 1) if last else size - 1
            else:
                start = max(0, size - int(last))
            if start > end or start >= size:
                self.send_response(416)
                self.send_header('Content-Range', f'bytes */{size}')
                self.end_headers()
                return
            status = 206
        self.send_response(status)
        self.send_header('Content-Type', 'audio/mpeg')
        self.send_header('Accept-Ranges', 'bytes')
        self.send_header('Content-Length', str(end - start + 1))
        if status == 206:
            self.send_header('Content-Range', f'bytes {start}-{end}/{size}')
        self.end_headers()
        try:
            with path.open('rb') as source:
                source.seek(start)
                remaining = end - start + 1
                while remaining:
                    chunk = source.read(min(65536, remaining))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    remaining -= len(chunk)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_POST(self):
        global worker, allowed_signs
        if self.path.startswith('/api/maps/'):
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 3 * 1024 * 1024:
                    raise ValueError('Map data is too large or empty.')
                track_id = unquote(self.path.rsplit('/', 1)[-1])
                song_row = next((row for row in music.tracks() if row['id'] == track_id), None)
                if song_row is None:
                    raise ValueError('Wait for this song to finish analysis before saving a map.')
                value = json.loads(self.rfile.read(length))
                self.json_response(save_map(music.root, track_id, value, song_row['duration']), 201)
            except (ValueError, OSError) as error:
                self.json_response({'error': str(error)}, 400)
            return
        if self.path == '/api/tracks/import':
            path = None
            try:
                length = int(self.headers.get('Content-Length', '0'))
                name = unquote(self.headers.get('X-Filename', '')).replace('\\', '/').rsplit('/', 1)[-1]
                if not name.lower().endswith('.mp3'):
                    raise ValueError('Choose an MP3 file.')
                if not 0 < length <= MAX_UPLOAD:
                    raise ValueError('Choose an MP3 file under 100 MB.')
                track_id = uuid.uuid4().hex
                music.root.mkdir(parents=True, exist_ok=True)
                path = music.root / f'{track_id}.mp3'
                remaining = length
                with path.open('wb') as output:
                    while remaining:
                        chunk = self.rfile.read(min(1024 * 1024, remaining))
                        if not chunk:
                            raise ValueError('Upload was interrupted. Please try again.')
                        output.write(chunk)
                        remaining -= len(chunk)
                music.submit(path, track_id, Path(name).stem[:120])
                self.json_response({'id': track_id}, 202)
            except (ValueError, OSError) as error:
                if path:
                    path.unlink(missing_ok=True)
                self.json_response({'error': str(error)}, 400)
            return
        if self.path == '/api/tracker/signs':
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 1024:
                    raise ValueError('Invalid request size')
                selected = json.loads(self.rfile.read(length)).get('signs')
                if (not isinstance(selected, list) or not 3 <= len(selected) <= 5
                        or any(not isinstance(sign, str) or sign not in SIGNS for sign in selected)
                        or len(set(selected)) != len(selected)):
                    raise ValueError('Choose 3 to 5 unique recorded signs')
                with lock:
                    allowed_signs = selected
                    state.update(sign='Unknown', distance=None)
            except (ValueError, AttributeError) as error:
                self.send_response(400)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': str(error)}).encode())
                return
        elif self.path == '/api/calibration/start':
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 1024:
                    raise ValueError('Invalid request size')
                request = json.loads(self.rfile.read(length))
                with lock:
                    if not running.is_set() or state['status'] != 'Tracking':
                        raise ValueError('Wait for the camera to start before recording')
                    calibration.start(request.get('sign'), time.monotonic())
            except (ValueError, OSError) as error:
                self.send_response(400)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': str(error)}).encode())
                return
        elif self.path == '/api/calibration/cancel':
            with lock:
                calibration.finish(cancelled=True)
        elif self.path == '/api/camera/start':
            if worker is None or not worker.is_alive():
                running.set()
                with lock:
                    state['status'] = 'Starting camera…'
                worker = threading.Thread(target=track, daemon=True)
                worker.start()
        elif self.path == '/api/camera/stop':
            running.clear()
            if worker is not None:
                worker.join(timeout=3)
            with lock:
                state.update(status='Camera off', sign='No hands', hands=[], shapes=[])
        else:
            self.send_error(404)
            return
        self.send_response(204)
        self.end_headers()


if __name__ == '__main__':
    music.start_watching()
    server = ThreadingHTTPServer(('127.0.0.1', 8765), Handler)
    print('Hand gesture rhythm game: http://127.0.0.1:8765', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        music.stop_watching()
        running.clear()
        with lock:
            calibration.finish(cancelled=True)
        server.server_close()
