"""Local MP3 library with background librosa beat analysis."""
import json
import math
import threading
import hashlib
import time
from urllib.parse import quote
from pathlib import Path
from maps import map_path

MUSIC_ROOT = Path(__file__).resolve().parent / 'songs'
MAX_UPLOAD = 100 * 1024 * 1024
MAX_DURATION = 20 * 60
ANALYSIS_VERSION = 2


def analyze_mp3(path, track_id, title, progress=lambda message: None):
    import librosa
    import numpy as np
    import soundfile as sf
    progress('Decoding audio')
    info = sf.info(str(path))
    if info.duration > MAX_DURATION:
        raise ValueError('Please choose a song under 20 minutes.')
    audio, sr = librosa.load(str(path), sr=22050, mono=True)
    duration = len(audio) / sr
    if duration < 5:
        raise ValueError('Choose a song at least 5 seconds long.')
    progress('Detecting beats (the first import may take longer)')
    envelope = librosa.onset.onset_strength(y=audio, sr=sr)
    # Default trimming can discard minutes of valid rhythm after a quieter section.
    tempo, beats = librosa.beat.beat_track(onset_envelope=envelope, sr=sr, units='time', trim=False)
    times = sorted(set(round(float(t), 6) for t in beats if math.isfinite(float(t)) and 0 <= t < duration))
    bpm = float(np.asarray(tempo).reshape(-1)[0])
    if len(times) < 4 or not math.isfinite(bpm) or bpm <= 0:
        raise ValueError('No usable beat pattern found. Try a song with a clearer rhythm.')
    track = {'id': track_id, 'title': title, 'bpm': round(bpm, 2), 'duration': duration,
             'seed': int(track_id[:8], 16) % 12, 'mood': f'Imported MP3 / {len(times)} detected beats',
             'imported': True, 'audioUrl': f'/songs/{quote(path.name)}', 'beats': times,
             'analysisVersion': ANALYSIS_VERSION}
    metadata = path.with_name(path.name + '.beats.json')
    temporary = metadata.with_suffix('.tmp')
    temporary.write_text(json.dumps(track, allow_nan=False), encoding='utf-8')
    temporary.replace(metadata)
    return track


class MusicLibrary:
    def __init__(self, root=MUSIC_ROOT):
        self.root = Path(root)
        self.jobs = {}
        self.lock = threading.Lock()
        self.analysis_lock = threading.Lock()
        self.observed = {}
        self.attempted = {}
        self.watching = threading.Event()

    def tracks(self):
        result = []
        if self.root.exists():
            for path in self.root.glob('*.beats.json'):
                try:
                    row = json.loads(path.read_text(encoding='utf-8'))
                    audio = path.with_name(path.name[:-len('.beats.json')])
                    if row.get('analysisVersion') in (1, ANALYSIS_VERSION) and audio.is_file():
                        stat = audio.stat()
                        if 'sourceSize' not in row or (row.get('sourceSize'),row.get('sourceMtimeNs')) == (stat.st_size,stat.st_mtime_ns):
                            custom = map_path(self.root, row['id'])
                            if custom.exists():
                                try:
                                    row['customMap'] = json.loads(custom.read_text(encoding='utf-8'))
                                except (OSError, ValueError):
                                    pass
                            result.append(row)
                except (OSError, ValueError):
                    continue
        return sorted(result, key=lambda row: row['title'].casefold())

    def submit(self, path, track_id, title):
        with self.lock:
            self.jobs[track_id] = {'id': track_id, 'filename': path.name, 'status': 'queued', 'message': 'Waiting for analysis'}
        threading.Thread(target=self._analyze, args=(path, track_id, title), daemon=True).start()

    def _analyze(self, path, track_id, title):
        def progress(message):
            with self.lock:
                self.jobs[track_id].update(status='analyzing', message=message)
        try:
            with self.analysis_lock:
                before = path.stat()
                track = analyze_mp3(path, track_id, title, progress)
                after = path.stat()
                if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                    path.with_name(path.name + '.beats.json').unlink(missing_ok=True)
                    raise ValueError('File changed during analysis; waiting for copying to finish.')
                track['sourceSize'] = after.st_size
                track['sourceMtimeNs'] = after.st_mtime_ns
                catalog = self.root / 'catalog.json'
                if catalog.exists():
                    demos = json.loads(catalog.read_text(encoding='utf-8'))
                    demo = next((row for row in demos if row.get('filename') == path.name), None)
                    if demo:
                        track.update(id=demo['id'], seed=demo['seed'], detectedBpm=track['bpm'],
                                     bpm=demo['bpm'], title=demo['title'], mood=demo['mood'])
                temporary = path.with_suffix('.tmp')
                temporary.write_text(json.dumps(track, allow_nan=False), encoding='utf-8')
                temporary.replace(path.with_name(path.name + '.beats.json'))
            with self.lock:
                self.jobs[track_id].update(status='complete', message='Beatmap ready', track=track)
        except Exception as error:
            with self.lock:
                self.jobs[track_id].update(status='error', message=f'Import failed: {error}')
            # Folder files belong to the user: keep failed MP3s for correction/retry.

    def job(self, track_id):
        with self.lock:
            return dict(self.jobs[track_id]) if track_id in self.jobs else None

    def scan(self):
        self.root.mkdir(parents=True, exist_ok=True)
        for path in self.root.iterdir():
            if not path.is_file() or path.suffix.lower() != '.mp3':
                continue
            try:
                stat = path.stat()
                signature = (stat.st_size, stat.st_mtime_ns)
                if self.observed.get(path.name) != signature:
                    self.observed[path.name] = signature
                    continue
                metadata = path.with_name(path.name + '.beats.json')
                if metadata.exists():
                    try:
                        row = json.loads(metadata.read_text(encoding='utf-8'))
                    except ValueError:
                        row = {}
                    if row.get('analysisVersion') == ANALYSIS_VERSION and (row.get('sourceSize'), row.get('sourceMtimeNs')) == signature:
                        continue
                track_id = hashlib.sha256(path.name.encode()).hexdigest()[:32]
                with self.lock:
                    busy = any(job.get('filename') == path.name and job['status'] in ('queued', 'analyzing')
                               for job in self.jobs.values())
                if busy or self.attempted.get(path.name) == signature:
                    continue
                self.attempted[path.name] = signature
                self.submit(path, track_id, path.stem)
            except (OSError, ValueError):
                continue

    def start_watching(self):
        if self.watching.is_set():
            return
        self.watching.set()
        def watch():
            while self.watching.is_set():
                self.scan()
                time.sleep(2)
        threading.Thread(target=watch, daemon=True).start()

    def stop_watching(self):
        self.watching.clear()

    def status(self):
        with self.lock:
            return [dict(job) for job in self.jobs.values()]
