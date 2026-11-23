"""SQLite prompt history, indexed Photo ID associations, and legacy JSON migration."""
import json
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

FIELDS = ('subject', 'appearance', 'hair_makeup', 'pose', 'expression',
          'environment', 'composition', 'lighting', 'finishing')
MAX_TEXT_LENGTH = 8000
PHOTO_ID_PATTERN = re.compile(r'[A-Za-z0-9!#$%*+\-./:;=?@_~]{1,24}\Z', re.ASCII)
DATA_DIR = Path(__file__).resolve().parent / 'data'
DB_FILE = DATA_DIR / 'prompt_history.sqlite3'
FILE = DATA_DIR / 'prompt_history.json'  # Legacy source; never modified by migration.
TEMPLATE_FILE = DATA_DIR / 'prompt_history_template.json'

# Text is stored once, with independent recency per field and one assignment per
# Photo ID/field. Composite foreign keys prevent dangling or mismatched mappings.
_SCHEMA = (
    'CREATE TABLE fields (name TEXT PRIMARY KEY)',
    'CREATE TABLE texts (id INTEGER PRIMARY KEY, text TEXT NOT NULL UNIQUE)',
    """CREATE TABLE history (
        field TEXT NOT NULL REFERENCES fields(name),
        text_id INTEGER NOT NULL REFERENCES texts(id),
        position INTEGER NOT NULL,
        PRIMARY KEY (field, text_id))""",
    'CREATE INDEX history_recent ON history(field, position DESC, text_id)',
    'CREATE INDEX history_text ON history(text_id)',
    """CREATE TABLE photo_fields (
        photo_id TEXT NOT NULL, field TEXT NOT NULL, text_id INTEGER NOT NULL,
        position INTEGER NOT NULL,
        PRIMARY KEY (photo_id, field),
        FOREIGN KEY (field, text_id) REFERENCES history(field, text_id) ON DELETE CASCADE)""",
    'CREATE INDEX photo_fields_history ON photo_fields(field, text_id, position)',
    """CREATE TRIGGER history_remove_text AFTER DELETE ON history BEGIN
        DELETE FROM texts WHERE id = OLD.text_id
            AND NOT EXISTS (SELECT 1 FROM history WHERE text_id = OLD.text_id);
    END""",
)


class PhotoIdConflict(Exception):
    def __init__(self, photo_id, fields):
        self.photo_id = photo_id
        self.fields = fields
        super().__init__('Photo ID is already assigned to different text in: ' + ', '.join(fields))


def _empty():
    return {'version': 2, 'history': {field: [] for field in FIELDS}}


def _validate_backup(data):
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
    return validated


def _legacy_data(source):
    try:
        data = json.loads(source.read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        raise RuntimeError(f'Unable to migrate prompt history from {source}: {exc}') from exc
    if (not isinstance(data, dict) or not isinstance(data.get('history'), dict)
            or type(data.get('version', 1)) is not int or data.get('version', 1) not in (1, 2)
            or any(field not in FIELDS for field in data['history'])):
        raise ValueError(f'Invalid legacy prompt history: {source}')
    normalized = _empty()
    for field in FIELDS:
        values = data['history'].get(field, [])
        if not isinstance(values, list):
            raise ValueError(f'{field} history must be a list')
        normalized['history'][field] = [
            {'text': item, 'photo_ids': []} if isinstance(item, str) else item
            for item in values
        ]
    return _validate_backup(normalized)


def _insert_backup(conn, data):
    for field, items in data['history'].items():
        for index, item in enumerate(items):
            conn.execute('INSERT OR IGNORE INTO texts(text) VALUES (?)', (item['text'],))
            text_id = conn.execute('SELECT id FROM texts WHERE text = ?', (item['text'],)).fetchone()[0]
            conn.execute('INSERT INTO history VALUES (?, ?, ?)', (field, text_id, len(items) - index))
            conn.executemany('INSERT INTO photo_fields VALUES (?, ?, ?, ?)',
                             [(photo_id, field, text_id, i) for i, photo_id in enumerate(item['photo_ids'])])


def _connect():
    DB_FILE.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_FILE), timeout=30, isolation_level=None)
    try:
        conn.execute('PRAGMA foreign_keys = ON')
        version = conn.execute('PRAGMA user_version').fetchone()[0]
        if version == 0:
            conn.execute('PRAGMA journal_mode = WAL')
            conn.execute('BEGIN IMMEDIATE')
            # A different process may have finished migration while we waited.
            if conn.execute('PRAGMA user_version').fetchone()[0] == 0:
                data = _legacy_data(FILE if FILE.exists() else TEMPLATE_FILE)
                for statement in _SCHEMA:
                    conn.execute(statement)
                conn.executemany('INSERT INTO fields VALUES (?)', [(field,) for field in FIELDS])
                _insert_backup(conn, data)
                conn.execute('PRAGMA user_version = 1')
            conn.commit()
        elif version != 1:
            raise RuntimeError(f'Unsupported prompt history database version: {version}')
        return conn
    except Exception:
        conn.close()  # Also rolls back an incomplete migration.
        raise


@contextmanager
def _database(write=False):
    conn = None
    try:
        conn = _connect()
        conn.execute('BEGIN IMMEDIATE' if write else 'BEGIN')
        yield conn
        conn.commit()
    except sqlite3.Error as exc:
        if conn is not None:
            conn.rollback()
        raise RuntimeError(f'Unable to access prompt history database: {exc}') from exc
    finally:
        if conn is not None:
            conn.close()


def migrate():
    """Initialize once, migrating legacy JSON (or the template) transactionally."""
    with _database():
        pass
    return DB_FILE


def _history(conn):
    result = {field: [] for field in FIELDS}
    for field, text in conn.execute(
            'SELECT h.field, t.text FROM history h JOIN texts t ON t.id = h.text_id '
            'ORDER BY h.field, h.position DESC, h.text_id'):
        result[field].append(text)
    return result


def _photo_ids(conn):
    result = {}
    for photo_id, field, text in conn.execute(
            'SELECT p.photo_id, p.field, t.text FROM photo_fields p '
            'JOIN texts t ON t.id = p.text_id ORDER BY p.photo_id, p.field'):
        result.setdefault(photo_id, {})[field] = text
    return result


def _state(conn, include_history=True):
    result = {'photo_ids': _photo_ids(conn)}
    if include_history:
        result['history'] = _history(conn)
    return result


def read_state(include_history=True):
    with _database() as conn:
        return _state(conn, include_history)


def read_history():
    with _database() as conn:
        return _history(conn)


def read_history_page(field, before=None, page_size=100):
    """Keyset pagination: read a bounded page through history_recent, not OFFSET."""
    if field not in FIELDS:
        raise ValueError('Invalid field')
    if type(page_size) is not int or not 1 <= page_size <= 200:
        raise ValueError('page_size must be an integer from 1 to 200')
    if before is not None and (type(before) is not int or before < 1):
        raise ValueError('before must be a positive integer')
    with _database() as conn:
        query = ('SELECT t.text, h.position, EXISTS ('
                 'SELECT 1 FROM photo_fields p WHERE p.field = h.field AND p.text_id = h.text_id'
                 ') FROM history h JOIN texts t ON t.id = h.text_id '
                 'WHERE h.field = ?')
        args = [field]
        if before is not None:
            query += ' AND h.position < ?'
            args.append(before)
        query += ' ORDER BY h.position DESC, h.text_id LIMIT ?'
        args.append(page_size + 1)
        rows = conn.execute(query, args).fetchall()
        page = rows[:page_size]
        return {'items': [row[0] for row in page],
                'has_photo_id': [bool(row[2]) for row in page],
                'next_cursor': page[-1][1] if len(rows) > page_size else None}


def read_photo_ids():
    with _database() as conn:
        return _photo_ids(conn)


def list_photo_ids():
    with _database() as conn:
        return [row[0] for row in conn.execute('SELECT DISTINCT photo_id FROM photo_fields ORDER BY photo_id')]


def read_photo_id(photo_id):
    with _database() as conn:
        values = dict(conn.execute(
            'SELECT p.field, t.text FROM photo_fields p JOIN texts t ON t.id = p.text_id '
            'WHERE p.photo_id = ?', (photo_id,)))
        return values or None


def export_data():
    """Keep the version 2 JSON backup format independent of database storage."""
    with _database() as conn:
        result = _empty()
        associations = {}
        for field, text_id, photo_id in conn.execute(
                'SELECT field, text_id, photo_id FROM photo_fields ORDER BY field, text_id, position'):
            associations.setdefault((field, text_id), []).append(photo_id)
        for field, text_id, text in conn.execute(
                'SELECT h.field, h.text_id, t.text FROM history h JOIN texts t ON t.id = h.text_id '
                'ORDER BY h.field, h.position DESC, h.text_id'):
            result['history'][field].append({'text': text, 'photo_ids': associations.get((field, text_id), [])})
        return result


def import_data(data):
    validated = _validate_backup(data)
    with _database(write=True) as conn:
        conn.execute('DELETE FROM history')
        _insert_backup(conn, validated)
        return _state(conn)


def _validate_photo_id(photo_id):
    if not isinstance(photo_id, str) or not PHOTO_ID_PATTERN.fullmatch(photo_id):
        raise ValueError('Photo ID must be 1–24 characters: A–Z, a–z, 0–9, or !#$%*+-./:;=?@_~')


def _has_id(conn, photo_id):
    return conn.execute('SELECT 1 FROM photo_fields WHERE photo_id = ? LIMIT 1', (photo_id,)).fetchone() is not None


def rename_photo_id(old_id, new_id, *, include_history=True):
    _validate_photo_id(old_id)
    _validate_photo_id(new_id)
    with _database(write=True) as conn:
        if not _has_id(conn, old_id):
            raise ValueError('Photo ID does not exist')
        if _has_id(conn, new_id):
            raise ValueError('New Photo ID is already in use')
        conn.execute('UPDATE photo_fields SET photo_id = ? WHERE photo_id = ?', (new_id, old_id))
        return _state(conn, include_history)


def delete_photo_id(photo_id, *, include_history=True):
    _validate_photo_id(photo_id)
    with _database(write=True) as conn:
        if not _has_id(conn, photo_id):
            raise ValueError('Photo ID does not exist')
        conn.execute('DELETE FROM photo_fields WHERE photo_id = ?', (photo_id,))
        return _state(conn, include_history)


def add_entries(entries, photo_id=None, enabled=None, overwrite=False, *,
                include_history=True, return_state=True):
    """Save without a retention cap; autosave can skip loading the shared state."""
    if not isinstance(entries, dict):
        raise ValueError('entries must be an object')
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
    with _database(write=True) as conn:
        if photo_id is not None:
            assigned = dict(conn.execute(
                'SELECT p.field, t.text FROM photo_fields p JOIN texts t ON t.id = p.text_id '
                'WHERE p.photo_id = ?', (photo_id,)))
            conflicts = [field for field, raw in entries.items()
                         if raw.strip() and (enabled is None or enabled.get(field, True))
                         and field in assigned and assigned[field] != raw.strip()]
            if conflicts and not overwrite:
                raise PhotoIdConflict(photo_id, conflicts)
            conn.execute('DELETE FROM photo_fields WHERE photo_id = ?', (photo_id,))
        for field, raw in entries.items():
            value = raw.strip()
            if not value:
                continue
            conn.execute('INSERT OR IGNORE INTO texts(text) VALUES (?)', (value,))
            text_id = conn.execute('SELECT id FROM texts WHERE text = ?', (value,)).fetchone()[0]
            position = conn.execute(
                'SELECT COALESCE(MAX(position), 0) + 1 FROM history WHERE field = ?', (field,)).fetchone()[0]
            conn.execute('INSERT INTO history VALUES (?, ?, ?) '
                         'ON CONFLICT(field, text_id) DO UPDATE SET position = excluded.position',
                         (field, text_id, position))
            if photo_id is not None and (enabled is None or enabled.get(field, True)):
                association_position = conn.execute(
                    'SELECT COALESCE(MAX(position), -1) + 1 FROM photo_fields WHERE field = ? AND text_id = ?',
                    (field, text_id)).fetchone()[0]
                conn.execute('INSERT INTO photo_fields VALUES (?, ?, ?, ?)',
                             (photo_id, field, text_id, association_position))
        result = _state(conn, include_history) if return_state else {}
        result['saved_photo_id'] = photo_id
        return result


def delete_entry(field, value, *, include_history=True):
    if field not in FIELDS or not isinstance(value, str):
        raise ValueError('Invalid field or value')
    with _database(write=True) as conn:
        conn.execute('DELETE FROM history WHERE field = ? AND text_id = (SELECT id FROM texts WHERE text = ?)',
                     (field, value))
        return _state(conn, include_history)


def clear_field(field, *, include_history=True):
    if field not in FIELDS:
        raise ValueError('Invalid field')
    with _database(write=True) as conn:
        conn.execute('DELETE FROM history WHERE field = ?', (field,))
        return _state(conn, include_history)
