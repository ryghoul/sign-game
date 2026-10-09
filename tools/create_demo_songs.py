"""Write the five existing synthesized demo tracks as MP3s into songs/."""
import json
from pathlib import Path
import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parent.parent / 'songs'

def create_demos():
    sr = 44100
    for track in json.loads((ROOT / 'catalog.json').read_text(encoding='utf-8')):
        path = ROOT / track['filename']
        if path.exists():
            continue
        audio = np.zeros(sr * 60, dtype=np.float32)
        def tone(start, frequency, duration, gain, triangle=False, sweep=False):
            offset = int(start * sr)
            count = min(int(duration * sr), len(audio) - offset)
            if count <= 0:
                return
            time = np.arange(count) / sr
            phase = np.cumsum(frequency * (.45 ** (time / duration) if sweep else np.ones(count))) / sr
            wave = 2 / np.pi * np.arcsin(np.sin(2 * np.pi * phase)) if triangle else np.sin(2 * np.pi * phase)
            envelope = np.exp(np.log(.001) * time / duration)
            envelope *= np.minimum(1, time / .002)
            audio[offset:offset + count] += (wave * envelope * gain).astype(np.float32)
        beat = 60 / track['bpm']
        for b in range(int(60 / beat)):
            start = b * beat
            tone(start, track['accent'] if b % 2 == 0 else track['accent'] * 1.6,
                 .16 if b % 2 == 0 else .07, .6, sweep=True)
            tone(start, 6000, .025, .08, triangle=True)
            if b % 2 == 0:
                tone(start, track['chords'][(b // 8) % 4], beat * .5, .12, triangle=track['wave']=='triangle')
            if (b + track['seed']) % 3 == 0:
                tone(start, track['melody'][(b + track['seed']) % 4], beat * .35, .07, sweep=True)
        sf.write(path, audio, sr, format='MP3')
        print(f"Created {path.name}", flush=True)

if __name__ == '__main__':
    create_demos()
