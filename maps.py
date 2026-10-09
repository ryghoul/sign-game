"""Validation and atomic persistence for custom song maps."""
import json
import math
import re
from recognition import SIGNS

def validate_map(value, duration):
    if not isinstance(value, dict):
        raise ValueError('Invalid map format')
    name = value.get('name')
    signs = value.get('signs')
    notes = value.get('notes')
    if not isinstance(name, str) or not 1 <= len(name.strip()) <= 120:
        raise ValueError('Give the map a name (up to 120 characters).')
    if (not isinstance(signs, list) or len(signs) != 5 or
            any(not isinstance(sign, str) or sign not in SIGNS for sign in signs) or len(set(signs)) != 5):
        raise ValueError('The map must use five unique sign slots.')
    if not isinstance(notes, list) or not 1 <= len(notes) <= 10000:
        raise ValueError('Add between 1 and 10,000 notes before saving.')
    cleaned = []
    for note in notes:
        if not isinstance(note, dict):
            raise ValueError('Invalid note format')
        time, length = note.get('time'), note.get('duration')
        lane, slot = note.get('lane'), note.get('signSlot')
        if (type(time) not in (int, float) or type(length) not in (int, float)
                or not math.isfinite(time) or not math.isfinite(length)
                or time < 0 or length < 0 or time + length > duration + .001):
            raise ValueError('Notes and hold tails must stay inside the song.')
        if type(lane) is not int or not 0 <= lane <= 3 or type(slot) is not int or not 0 <= slot <= 4:
            raise ValueError('Choose a valid lane and sign slot for every note.')
        cleaned.append({'time': round(time, 6), 'duration': round(length, 6), 'lane': lane, 'signSlot': slot})
    return {'version': 1, 'name': name.strip(), 'signs': signs,
            'notes': sorted(cleaned, key=lambda note: (note['time'], note['lane']))}

def map_path(root, track_id):
    if not re.fullmatch(r'[a-zA-Z0-9_-]{1,80}', track_id):
        raise ValueError('Invalid track ID')
    return root / 'maps' / f'{track_id}.json'

def save_map(root, track_id, value, duration):
    result = validate_map(value, duration)
    path = map_path(root, track_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(result, allow_nan=False), encoding='utf-8')
    temporary.replace(path)
    return result
