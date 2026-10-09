import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
import soundfile as sf

from music import ANALYSIS_VERSION, MusicLibrary, analyze_mp3


class MusicTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)

    def test_mp3_beats_and_persistence(self):
        sr = 22050
        audio = np.zeros(sr * 16, dtype=np.float32)
        for beat in np.arange(.5, 15.5, .5):
            start = int(beat * sr)
            time = np.arange(1100) / sr
            audio[start:start + 1100] += (np.sin(2 * np.pi * 180 * time) * np.exp(-time * 95)).astype(np.float32)
        path = self.root / ('a' * 32 + '.mp3')
        sf.write(path, audio, sr, format='MP3')
        result = analyze_mp3(path, 'a' * 32, 'Known 120 BPM rhythm')
        self.assertTrue(110 < result['bpm'] < 130)
        self.assertGreater(len(result['beats']), 20)
        self.assertEqual(result['beats'], sorted(set(result['beats'])))
        self.assertTrue(all(0 <= t < result['duration'] for t in result['beats']))
        self.assertEqual(MusicLibrary(self.root).tracks(), [result])
        self.assertEqual(json.loads(path.with_name(path.name + '.beats.json').read_text()), result)

    def test_folder_scanner_waits_for_stable_files_and_retries_changes(self):
        library = MusicLibrary(self.root)
        calls = []
        def record(path, track_id, title):
            calls.append((path, title))
            library.jobs[track_id] = {'status':'error', 'filename':path.name}
        library.submit = record
        path = self.root / 'A Song.MP3'
        path.write_bytes(b'audio')
        library.scan()
        self.assertEqual(calls, [])
        library.scan()
        self.assertEqual(len(calls), 1)
        library.scan()
        self.assertEqual(len(calls), 1)
        path.write_bytes(b'new audio')
        library.scan()
        self.assertEqual(len(calls), 1)
        library.scan()
        self.assertEqual(len(calls), 2)
        self.assertTrue(path.exists())

    def test_silence_is_rejected(self):
        path = self.root / ('b' * 32 + '.mp3')
        sf.write(path, np.zeros(22050 * 8), 22050, format='MP3')
        with self.assertRaisesRegex(ValueError, 'No usable beat'):
            analyze_mp3(path, 'b' * 32, 'Silent song')
        self.assertFalse(path.with_name(path.name + '.beats.json').exists())

    def test_quieter_second_half_keeps_beats(self):
        sr = 22050
        audio = np.zeros(sr * 30, dtype=np.float32)
        for beat in np.arange(.5, 29.5, .5):
            start = int(beat * sr)
            time = np.arange(1100) / sr
            gain = 1 if beat < 15 else .04
            audio[start:start + 1100] += (gain * np.sin(2 * np.pi * 180 * time) * np.exp(-time * 95)).astype(np.float32)
        path = self.root / ('d' * 32 + '.mp3')
        sf.write(path, audio, sr, format='MP3')
        result = analyze_mp3(path, 'd' * 32, 'Quieter ending')
        self.assertGreater(result['beats'][-1], 28)
        self.assertGreater(sum(t > 15 for t in result['beats']), 20)

    def test_old_analysis_is_refreshed_without_changing_audio(self):
        path = self.root / 'Old.mp3'
        path.write_bytes(b'audio')
        stat = path.stat()
        metadata = path.with_name(path.name + '.beats.json')
        metadata.write_text(json.dumps({'analysisVersion': 1, 'sourceSize': stat.st_size,
                                        'sourceMtimeNs': stat.st_mtime_ns}))
        library = MusicLibrary(self.root)
        calls = []
        library.submit = lambda *args: calls.append(args)
        library.scan()
        library.scan()
        self.assertEqual(len(calls), 1)
        row = json.loads(metadata.read_text())
        row['analysisVersion'] = ANALYSIS_VERSION
        metadata.write_text(json.dumps(row))
        library = MusicLibrary(self.root)
        library.submit = lambda *args: calls.append(args)
        library.scan()
        library.scan()
        self.assertEqual(len(calls), 1)
        self.assertEqual(path.read_bytes(), b'audio')

    def test_failed_import_reports_error_and_preserves_file(self):
        path = self.root / ('c' * 32 + '.mp3')
        path.write_bytes(b'not audio')
        library = MusicLibrary(self.root)
        library.jobs['c' * 32] = {'id': 'c' * 32, 'status': 'queued'}
        library._analyze(path, 'c' * 32, 'Invalid file')
        self.assertEqual(library.job('c' * 32)['status'], 'error')
        self.assertTrue(path.exists())
        self.assertEqual(library.tracks(), [])


if __name__ == '__main__':
    unittest.main()
