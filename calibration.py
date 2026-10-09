"""Timed replacement recordings. Caller serializes access with the tracker lock."""
import json
from copy import deepcopy
from pathlib import Path
from recognition import SIGNS, DATA_PATH

class Calibration:
    def __init__(self, samples, path=DATA_PATH):
        self.samples = samples
        self.path = Path(path)
        self.sign = None
        self.started = 0
        self.rows = []
        self.status = 'idle'
        self.error = None

    def save(self, sign, rows):
        updated = dict(self.samples)
        updated[sign] = rows
        temporary = self.path.with_suffix('.tmp')
        temporary.write_text(json.dumps({'version': 1, 'signs': updated}), encoding='utf-8')
        temporary.replace(self.path)
        self.samples[sign] = rows

    def start(self, sign, now):
        if sign not in SIGNS:
            raise ValueError('Unknown sign')
        if self.sign is not None:
            raise ValueError('A calibration is already recording')
        self.save(sign, [])
        self.sign, self.started = sign, now
        self.rows = []
        self.status, self.error = 'recording', None

    def update(self, pose, now):
        if self.sign is None:
            return
        if now - self.started >= 15:
            self.finish()
        elif len(pose['hands']) == 2 and {h['handedness'] for h in pose['hands']} == {'left', 'right'}:
            self.rows.append(deepcopy(pose))

    def finish(self, cancelled=False):
        if self.sign is None:
            return
        sign = self.sign
        try:
            self.save(sign, self.rows)
            self.status = 'cancelled' if cancelled else 'complete'
        except OSError as error:
            self.status, self.error = 'error', str(error)
        self.sign = None

    def snapshot(self, now):
        return {'status': self.status, 'sign': self.sign, 'count': len(self.rows),
                'remaining': max(0, 15 - (now - self.started)) if self.sign else 0,
                'error': self.error}
