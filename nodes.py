"""ComfyUI nodes for editing and reading photographic prompts."""
import json
from datetime import datetime

from .history import FIELDS, MAX_TEXT_LENGTH, PHOTO_ID_PATTERN, add_entries, list_photo_ids, read_photo_id

_MISSING_TITLE = object()

HEADINGS = {
    'subject': 'Subject',
    'appearance': 'Clothing',
    'hair_makeup': 'Hair & Makeup',
    'pose': 'Posing',
    'expression': 'Expression',
    'environment': 'Environment',
    'composition': 'Composition & Camera',
    'lighting': 'Lighting',
    'finishing': 'Finishing',
}


def compose_prompt(values, enabled):
    parts = []
    for field in FIELDS:
        text = values.get(field, '')
        if enabled.get(field, True) and isinstance(text, str) and text.strip():
            parts.append(f'{HEADINGS[field]}:\n{text.strip()}')
    return '\n\n'.join(parts)


def _parse_image_tags_with_title(raw):
    """Validate one VLM response before it can enter shared history."""
    if not isinstance(raw, str):
        raise ValueError('tags_json must be a JSON string')
    try:
        values = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f'tags_json must contain one JSON object: {exc.msg}') from exc
    if not isinstance(values, dict) or set(values) - {'title'} != set(FIELDS):
        raise ValueError('tags_json must contain the nine photo prompt fields and optional title')
    if any(not isinstance(values[field], str) or len(values[field]) > MAX_TEXT_LENGTH
           for field in FIELDS):
        raise ValueError('Each photo prompt field must be a string of at most 8000 characters')
    title = values.get('title', _MISSING_TITLE)
    values = {field: values[field].strip() for field in FIELDS}
    if not any(values.values()):
        raise ValueError('At least one photo prompt field must be nonempty')
    return values, title


def parse_image_tags(raw):
    return _parse_image_tags_with_title(raw)[0]


class Krea2ImageToTextSave:
    CATEGORY = 'prompt/photo'
    FUNCTION = 'process'
    RETURN_TYPES = ('STRING', 'STRING')
    RETURN_NAMES = ('prompt', 'photo_id')
    OUTPUT_NODE = True
    DESCRIPTION = 'Validate nine JSON image tags and save them automatically or with a Save button.'

    @classmethod
    def INPUT_TYPES(cls):
        return {'required': {
            'tags_json': ('STRING', {'default': '', 'multiline': True, 'dynamicPrompts': False}),
            'save_mode': (['Auto', 'Manual'], {'default': 'Manual'}),
            'photo_id': ('STRING', {'default': '', 'multiline': False, 'dynamicPrompts': False}),
            'overwrite': ('BOOLEAN', {'default': False}),
        }}

    def process(self, tags_json, save_mode='Manual', photo_id='', overwrite=False):
        values, title = _parse_image_tags_with_title(tags_json)
        if save_mode not in ('Auto', 'Manual'):
            raise ValueError('save_mode must be Auto or Manual')
        if not isinstance(photo_id, str):
            raise ValueError('photo_id must be a string')
        if not photo_id and title is not _MISSING_TITLE and not isinstance(title, str):
            raise ValueError('title must be a string when used as Photo ID')
        chosen_id = photo_id or (title.replace(' ', '_') if title is not _MISSING_TITLE
                                 else datetime.now().strftime('%y%m%d%H%M%S'))
        if not PHOTO_ID_PATTERN.fullmatch(chosen_id):
            raise ValueError('Photo ID must be 1–24 allowed ASCII characters')
        if type(overwrite) is not bool:
            raise ValueError('overwrite must be a boolean')
        if save_mode == 'Auto':
            add_entries(values, photo_id=chosen_id, overwrite=overwrite, return_state=False)
        payload = {'entries': values, 'photo_id': chosen_id, 'overwrite': overwrite,
                   'saved': save_mode == 'Auto'}
        return {'ui': {'image_to_text': [payload]},
                'result': (compose_prompt(values, {}), chosen_id)}


class Krea2PhotoPromptBuilder:
    CATEGORY = 'prompt/photo'
    FUNCTION = 'build'
    RETURN_TYPES = ('STRING',)
    RETURN_NAMES = ('prompt',)
    OUTPUT_NODE = False
    DESCRIPTION = 'Nine-section photographic prompt builder with reusable local SQLite history.'

    @classmethod
    def INPUT_TYPES(cls):
        required = {}
        for key in FIELDS:
            required[key] = ('STRING', {'default': '', 'multiline': True, 'dynamicPrompts': False})
        required['auto_save_history'] = ('BOOLEAN', {'default': True, 'label_on': 'On', 'label_off': 'Off'})
        required['photo_id'] = ('STRING', {'default': '', 'multiline': False})
        return {'required': required, 'hidden': {'prompt': 'PROMPT', 'unique_id': 'UNIQUE_ID'}}

    def build(self, prompt=None, unique_id=None, **kwargs):
        values = {key: kwargs.get(key, '') for key in FIELDS}
        inputs = (prompt or {}).get(str(unique_id), {}).get('inputs', {})
        enabled = {key: not (isinstance(inputs.get(key), list) and
                             len(inputs[key]) == 2) for key in FIELDS}
        prompt = compose_prompt(values, enabled)
        if kwargs.get('auto_save_history', True):
            try:
                add_entries(values, enabled=enabled, return_state=False)
            except (OSError, ValueError, RuntimeError) as e:
                print(f'[Krea2 Photo Prompt Builder] Cannot save history: {e}')
        return (prompt,)


NODE_ID = 'MagichanLab_Krea2PhotoPromptBuilder'
REFERENCE_NODE_ID = 'MagichanLab_Krea2PhotoPromptReference'
IMAGE_TO_TEXT_NODE_ID = 'MagichanLab_Krea2ImageToTextSave'
SELECT_PHOTO_ID = '(Select Photo ID)'


class Krea2PhotoPromptReference:
    CATEGORY = 'prompt/photo'
    FUNCTION = 'build'
    RETURN_TYPES = ('STRING',)
    RETURN_NAMES = ('prompt',)
    DESCRIPTION = 'Read a saved Photo ID combination without changing prompt history.'

    @classmethod
    def INPUT_TYPES(cls):
        return {'required': {'photo_id': ([SELECT_PHOTO_ID, *list_photo_ids()],
                                          {'default': SELECT_PHOTO_ID})},
                'optional': {
                    'additional_tag': (list(HEADINGS.values()), {'default': 'Subject'}),
                    'additional_prompt': ('STRING', {'default': '', 'multiline': False,
                                                     'dynamicPrompts': False}),
                }}

    @classmethod
    def IS_CHANGED(cls, photo_id, additional_tag='Subject', additional_prompt=''):
        # Invalidate ComfyUI's execution cache when a saved combination changes.
        return json.dumps(read_photo_id(photo_id), ensure_ascii=False, sort_keys=True)

    def build(self, photo_id, additional_tag='Subject', additional_prompt=''):
        if not photo_id or photo_id == SELECT_PHOTO_ID:
            raise ValueError('Select a Photo ID before running the reference node.')
        values = read_photo_id(photo_id)
        if values is None:
            raise ValueError(f'Photo ID "{photo_id}" does not exist in saved history.')
        if additional_prompt.strip():
            field = next((key for key, label in HEADINGS.items() if label == additional_tag), None)
            if field is None:
                raise ValueError(f'Unknown additional prompt tag: {additional_tag}')
            values = dict(values)
            values[field] = '\n'.join(filter(None, [values.get(field, '').strip(),
                                                     additional_prompt.strip()]))
        return (compose_prompt(values, {}),)


NODE_CLASS_MAPPINGS = {
    NODE_ID: Krea2PhotoPromptBuilder,
    REFERENCE_NODE_ID: Krea2PhotoPromptReference,
    IMAGE_TO_TEXT_NODE_ID: Krea2ImageToTextSave,
}
NODE_DISPLAY_NAME_MAPPINGS = {
    NODE_ID: 'Krea2 Photo Prompt Builder',
    REFERENCE_NODE_ID: 'Krea2 Photo Prompt Reference',
    IMAGE_TO_TEXT_NODE_ID: 'Krea2 Image to Text Save',
}
