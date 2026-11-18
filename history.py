"""Thread-safe JSON prompt history and Photo ID associations."""
import json
import os
import re
from datetime import datetime
from pathlib import Path
from threading import RLock

FIELDS = ('subject', 'appearance', 'hair_makeup', 'pose', 'expression',
          'environment', 'composition', 'lighting', 'finishing')
MAX_TEXT_LENGTH = 8000
DEFAULT_LIMIT = 100
PHOTO_ID_PATTERN = re.compile(r'[A-Za-z0-9!#$%*+\-./:;=?@_~]{1,24}\Z', re.ASCII)
_LOCK = RLock()
FILE = Path(__file__).resolve().parent / 'data' / 'prompt_history.json'
TEMPLATE_FILE = Path(__file__).resolve().parent / 'data' / 'prompt_history_template.json'


class PhotoIdConflict(Exception):
    def __init__(self, photo_id, fields):
        self.photo_id = photo_id
        self.fields = fields
        super().__init__('Photo ID is already assigned to different text in: ' + ', '.join(fields))


def _empty():
    return {'version': 2, 'history': {field: [] for field in FIELDS}}


def _read_unlocked():
    source = FILE if FILE.exists() else TEMPLATE_FILE
    try:
        with source.open('r', encoding='utf-8') as f:
            obj = json.load(f)
    except (OSError, ValueError) as e:
        raise RuntimeError(f'Unable to read prompt history: {e}') from e
    if not isinstance(obj, dict) or not isinstance(obj.get('history'), dict):
        raise ValueError('Invalid prompt history JSON format')
    result = _empty()
    for field in FIELDS:
        values = obj['history'].get(field, [])
        if not isinstance(values, list):
            continue
        seen = set()
        seen_ids = set()
        for item in values:
            if isinstance(item, str):
                text, ids = item, []
            elif isinstance(item, dict):
                text, ids = item.get('text'), item.get('photo_ids', [])
            else:
                continue
            if not isinstance(text, str) or text in seen or len(text) > MAX_TEXT_LENGTH:
                continue
            seen.add(text)
            if not isinstance(ids, list):
                ids = []
            valid_ids = [i for i in ids if isinstance(i, str) and PHOTO_ID_PATTERN.fullmatch(i) and i not in seen_ids]
            unique_ids = list(dict.fromkeys(valid_ids))
            seen_ids.update(unique_ids)
            result['history'][field].append({
                'text': text,
                'photo_ids': unique_ids,
            })
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


def _public(data):
    return {field: [item['text'] for item in data['history'][field]] for field in FIELDS}


def _photo_ids(data):
    result = {}
    for field in FIELDS:
        for item in data['history'][field]:
            for photo_id in item['photo_ids']:
                result.setdefault(photo_id, {})[field] = item['text']
    return result


def read_state():
    with _LOCK:
        data = _read_unlocked()
        return {'history': _public(data), 'photo_ids': _photo_ids(data)}


def export_data():
    """Return the complete on-disk schema, including Photo ID associations."""
    with _LOCK:
        return _read_unlocked()


def import_data(data):
    """Validate a version 2 backup and atomically replace the current history."""
    if (not isinstance(data, dict) or set(data) != {'version', 'history'}
            or type(data['version']) is not int or data['version'] != 2):
        raise ValueError('Expected a version 2 prompt history JSON object')
    history = data['history']
    if not isinstance(history, dict) or set(history) != set(FIELDS):
        raise ValueError('History must contain exactly the nine prompt fields')
    validated = _empty()
    for field in FIELDS:
        items = history[field]
        if not isinstance(items, list):
            raise ValueError(f'{field} history must be a list')
        seen_text = set()
        seen_ids = set()
        for item in items:
            if not isinstance(item, dict) or set(item) != {'text', 'photo_ids'}:
                raise ValueError(f'{field} entries must contain text and photo_ids')
            value, photo_ids = item['text'], item['photo_ids']
            if not isinstance(value, str) or not value or len(value) > MAX_TEXT_LENGTH or value in seen_text:
                raise ValueError(f'{field} contains invalid or duplicate text')
            if not isinstance(photo_ids, list) or any(
                not isinstance(photo_id, str) or not PHOTO_ID_PATTERN.fullmatch(photo_id)
                or photo_id in seen_ids for photo_id in photo_ids
            ) or len(photo_ids) != len(set(photo_ids)):
                raise ValueError(f'{field} contains invalid or duplicate Photo IDs')
            seen_text.add(value)
            seen_ids.update(photo_ids)
            validated['history'][field].append({'text': value, 'photo_ids': list(photo_ids)})
    with _LOCK:
        _write_unlocked(validated)
        return {'history': _public(validated), 'photo_ids': _photo_ids(validated)}


def read_history():
    return read_state()['history']


def read_photo_ids():
    return read_state()['photo_ids']


def _validate_photo_id(photo_id):
    if not isinstance(photo_id, str) or not PHOTO_ID_PATTERN.fullmatch(photo_id):
        raise ValueError('Photo ID must be 1–24 characters: A–Z, a–z, 0–9, or !#$%*+-./:;=?@_~')


def rename_photo_id(old_id, new_id):
    _validate_photo_id(old_id)
    _validate_photo_id(new_id)
    with _LOCK:
        data = _read_unlocked()
        ids = _photo_ids(data)
        if old_id not in ids:
            raise ValueError('Photo ID does not exist')
        if new_id in ids:
            raise ValueError('New Photo ID is already in use')
        for items in data['history'].values():
            for item in items:
                item['photo_ids'] = [new_id if value == old_id else value
                                     for value in item['photo_ids']]
        _write_unlocked(data)
        return {'history': _public(data), 'photo_ids': _photo_ids(data)}


def delete_photo_id(photo_id):
    _validate_photo_id(photo_id)
    with _LOCK:
        data = _read_unlocked()
        if photo_id not in _photo_ids(data):
            raise ValueError('Photo ID does not exist')
        for items in data['history'].values():
            for item in items:
                if photo_id in item['photo_ids']:
                    item['photo_ids'].remove(photo_id)
        _write_unlocked(data)
        return {'history': _public(data), 'photo_ids': _photo_ids(data)}


def add_entries(entries, limit=DEFAULT_LIMIT, photo_id=None, enabled=None, overwrite=False):
    """Save strings; require confirmation before moving an ID to different text."""
    if not isinstance(entries, dict):
        raise ValueError('entries must be an object')
    if type(limit) is not int or not (1 <= limit <= 1000):
        raise ValueError('limit must be an integer from 1 to 1000')
    if any(k not in FIELDS for k in entries):
        raise ValueError('Unknown field')
    if any(not isinstance(v, str) or len(v) > MAX_TEXT_LENGTH for v in entries.values()):
        raise ValueError('Each value must be a string of at most 8000 characters')
    if enabled is not None and (not isinstance(enabled, dict) or
                                any(k not in FIELDS or type(v) is not bool for k, v in enabled.items())):
        raise ValueError('enabled must contain boolean field values')
    if type(overwrite) is not bool:
        raise ValueError('overwrite must be a boolean')
    if photo_id is not None:
        if photo_id == '':
            photo_id = datetime.now().strftime('%y%m%d%H%M%S')
        _validate_photo_id(photo_id)
        if not any(raw.strip() and (enabled is None or enabled.get(field, True))
                   for field, raw in entries.items()):
            raise ValueError('At least one enabled, nonempty field is required for a Photo ID')
    with _LOCK:
        data = _read_unlocked()
        if photo_id is not None and not overwrite:
            assigned = _photo_ids(data).get(photo_id, {})
            conflicts = [field for field, raw in entries.items()
                         if raw.strip() and (enabled is None or enabled.get(field, True))
                         and field in assigned and assigned[field] != raw.strip()]
            if conflicts:
                raise PhotoIdConflict(photo_id, conflicts)
        before = json.dumps(data, ensure_ascii=False)
        if photo_id is not None:
            for items in data['history'].values():
                for item in items:
                    if photo_id in item['photo_ids']:
                        item['photo_ids'].remove(photo_id)
        for field, raw in entries.items():
            value = raw.strip()
            if not value:
                continue
            items = data['history'][field]
            existing = next((item for item in items if item['text'] == value), None)
            if existing is None:
                existing = {'text': value, 'photo_ids': []}
            else:
                items.remove(existing)
            if photo_id is not None and (enabled is None or enabled.get(field, True)):
                existing['photo_ids'].append(photo_id)
            items.insert(0, existing)
        # Tagged entries survive the history limit so saved combinations remain available.
        for field in FIELDS:
            untagged = 0
            kept = []
            for item in data['history'][field]:
                if item['photo_ids'] or untagged < limit:
                    kept.append(item)
                    if not item['photo_ids']:
                        untagged += 1
            data['history'][field] = kept
        if json.dumps(data, ensure_ascii=False) != before:
            _write_unlocked(data)
        return {'history': _public(data), 'photo_ids': _photo_ids(data), 'saved_photo_id': photo_id}


def delete_entry(field, value):
    if field not in FIELDS or not isinstance(value, str):
        raise ValueError('Invalid field or value')
    with _LOCK:
        data = _read_unlocked()
        old = data['history'][field]
        data['history'][field] = [item for item in old if item['text'] != value]
        if data['history'][field] != old:
            _write_unlocked(data)
        return {'history': _public(data), 'photo_ids': _photo_ids(data)}


def clear_field(field):
    if field not in FIELDS:
        raise ValueError('Invalid field')
    with _LOCK:
        data = _read_unlocked()
        if data['history'][field]:
            data['history'][field] = []
            _write_unlocked(data)
        return {'history': _public(data), 'photo_ids': _photo_ids(data)}
