"""ComfyUI nodes for editing and reading photographic prompts."""
import json

from .history import FIELDS, add_entries, read_photo_ids

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


class Krea2PhotoPromptBuilder:
    CATEGORY = 'prompt/photo'
    FUNCTION = 'build'
    RETURN_TYPES = ('STRING',)
    RETURN_NAMES = ('prompt',)
    OUTPUT_NODE = False
    DESCRIPTION = 'Nine-section photographic prompt builder with reusable local JSON history.'

    @classmethod
    def INPUT_TYPES(cls):
        required = {}
        for key in FIELDS:
            required[key] = ('STRING', {'default': '', 'multiline': True, 'dynamicPrompts': False})
            required[f'use_{key}'] = ('BOOLEAN', {'default': True, 'label_on': 'Include', 'label_off': 'Exclude'})
        required['auto_save_history'] = ('BOOLEAN', {'default': True, 'label_on': 'On', 'label_off': 'Off'})
        required['history_limit'] = ('INT', {'default': 100, 'min': 1, 'max': 1000, 'step': 1})
        required['photo_id'] = ('STRING', {'default': '', 'multiline': False})
        return {'required': required}

    def build(self, **kwargs):
        values = {key: kwargs.get(key, '') for key in FIELDS}
        enabled = {key: kwargs.get(f'use_{key}', True) for key in FIELDS}
        prompt = compose_prompt(values, enabled)
        if kwargs.get('auto_save_history', True):
            try:
                add_entries(values, limit=kwargs.get('history_limit', 100))
            except (OSError, ValueError, RuntimeError) as e:
                print(f'[Krea2 Photo Prompt Builder] Cannot save history: {e}')
        return (prompt,)


NODE_ID = 'MagichanLab_Krea2PhotoPromptBuilder'
REFERENCE_NODE_ID = 'MagichanLab_Krea2PhotoPromptReference'
SELECT_PHOTO_ID = '(Select Photo ID)'


class Krea2PhotoPromptReference:
    CATEGORY = 'prompt/photo'
    FUNCTION = 'build'
    RETURN_TYPES = ('STRING',)
    RETURN_NAMES = ('prompt',)
    DESCRIPTION = 'Read a saved Photo ID combination without changing prompt history.'

    @classmethod
    def INPUT_TYPES(cls):
        return {'required': {'photo_id': ([SELECT_PHOTO_ID, *sorted(read_photo_ids())],
                                          {'default': SELECT_PHOTO_ID})}}

    @classmethod
    def IS_CHANGED(cls, photo_id):
        # Invalidate ComfyUI's execution cache when a saved combination changes.
        return json.dumps(read_photo_ids().get(photo_id), ensure_ascii=False, sort_keys=True)

    def build(self, photo_id):
        if not photo_id or photo_id == SELECT_PHOTO_ID:
            raise ValueError('Select a Photo ID before running the reference node.')
        values = read_photo_ids().get(photo_id)
        if values is None:
            raise ValueError(f'Photo ID "{photo_id}" does not exist in saved history.')
        return (compose_prompt(values, {}),)


NODE_CLASS_MAPPINGS = {
    NODE_ID: Krea2PhotoPromptBuilder,
    REFERENCE_NODE_ID: Krea2PhotoPromptReference,
}
NODE_DISPLAY_NAME_MAPPINGS = {
    NODE_ID: 'Krea2 Photo Prompt Builder',
    REFERENCE_NODE_ID: 'Krea2 Photo Prompt Reference',
}
