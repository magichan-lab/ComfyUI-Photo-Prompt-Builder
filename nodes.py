"""ComfyUI legacy-style node. Inputs remain regular workflow-serializable widgets."""
from .history import FIELDS, add_entries

HEADINGS = {
    'subject': 'Subject',
    'appearance': 'Appearance',
    'pose': 'Pose & Expression',
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
    DESCRIPTION = 'Seven-section photographic prompt builder with reusable local JSON history.'

    @classmethod
    def INPUT_TYPES(cls):
        required = {}
        for key in FIELDS:
            required[key] = ('STRING', {'default': '', 'multiline': True, 'dynamicPrompts': False})
            required[f'use_{key}'] = ('BOOLEAN', {'default': True, 'label_on': 'Include', 'label_off': 'Exclude'})
        required['auto_save_history'] = ('BOOLEAN', {'default': True, 'label_on': 'On', 'label_off': 'Off'})
        required['history_limit'] = ('INT', {'default': 100, 'min': 1, 'max': 1000, 'step': 1})
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
NODE_CLASS_MAPPINGS = {NODE_ID: Krea2PhotoPromptBuilder}
NODE_DISPLAY_NAME_MAPPINGS = {NODE_ID: 'Krea2 Photo Prompt Builder'}
