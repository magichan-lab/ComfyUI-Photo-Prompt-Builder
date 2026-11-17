"""Thread-safe JSON prompt history stored inside this custom-node directory."""
import json
import os
from pathlib import Path
from threading import RLock

FIELDS = ('subject', 'appearance', 'hair_makeup', 'pose', 'expression',
          'environment', 'composition', 'lighting', 'finishing')
MAX_TEXT_LENGTH = 8000
DEFAULT_LIMIT = 100
_LOCK = RLock()
FILE = Path(__file__).resolve().parent / 'data' / 'prompt_history.json'


def _empty():
    return {'version': 1, 'history': {field: [] for field in FIELDS}}


def _read_unlocked():
    if not FILE.exists():
        return _empty()
    try:
        with FILE.open('r', encoding='utf-8') as f:
            obj = json.load(f)
    except (OSError, ValueError) as e:
        raise RuntimeError(f'Unable to read prompt history: {e}') from e
    if not isinstance(obj, dict) or not isinstance(obj.get('history'), dict):
        raise ValueError('Invalid prompt history JSON format')
    result = _empty()
    for key in FIELDS:
        values = obj['history'].get(key, [])
        if isinstance(values, list):
            result['history'][key] = [v for v in values if isinstance(v, str)][:1000]
    return result


def _write_unlocked(data):
    FILE.parent.mkdir(parents=True, exist_ok=True)
    temp = FILE.with_suffix('.json.tmp')
    try:
        with temp.open('w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write('\n')
        os.replace(temp, FILE)
    finally:
        if temp.exists():
            temp.unlink()


def read_history():
    with _LOCK:
        return _read_unlocked()['history']


def add_entries(entries, limit=DEFAULT_LIMIT):
    """Newest first, deduplicated, one history per field. Returns updated history."""
    if not isinstance(entries, dict):
        raise ValueError('entries must be an object')
    if type(limit) is not int or not (1 <= limit <= 1000):
        raise ValueError('limit must be an integer from 1 to 1000')
    if any(k not in FIELDS for k in entries):
        raise ValueError('Unknown field')
    if any(not isinstance(v, str) or len(v) > MAX_TEXT_LENGTH for v in entries.values()):
        raise ValueError('Each value must be a string of at most 8000 characters')
    with _LOCK:
        data = _read_unlocked()
        changed = False
        for key, raw in entries.items():
            value = raw.strip()
            if not value:
                continue
            existing = data['history'][key]
            updated = [value] + [v for v in existing if v != value]
            updated = updated[:limit]
            if updated != existing:
                data['history'][key] = updated
                changed = True
        if changed:
            _write_unlocked(data)
        return data['history']


def delete_entry(field, value):
    if field not in FIELDS or not isinstance(value, str):
        raise ValueError('Invalid field or value')
    with _LOCK:
        data = _read_unlocked()
        old = data['history'][field]
        data['history'][field] = [v for v in old if v != value]
        if data['history'][field] != old:
            _write_unlocked(data)
        return data['history']


def clear_field(field):
    if field not in FIELDS:
        raise ValueError('Invalid field')
    with _LOCK:
        data = _read_unlocked()
        if data['history'][field]:
            data['history'][field] = []
            _write_unlocked(data)
        return data['history']
