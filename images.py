"""Look up example images and save thumbnails from completed ComfyUI prompts."""
from pathlib import Path
import os
from uuid import uuid4

from .history import FIELDS, PHOTO_ID_PATTERN

IMAGE_DIR = Path(__file__).resolve().parent / 'data' / 'images'
IMAGE_EXTENSIONS = ('.png', '.jpg', '.jpeg', '.webp', '.gif')
THUMBNAIL_SIZE = (256, 256)


def photo_images():
    """Return one safe local image per filename-compatible Photo ID."""
    if not IMAGE_DIR.is_dir():
        return {}
    found = {}
    for path in IMAGE_DIR.iterdir():
        photo_id = path.stem
        extension = path.suffix.lower()
        if (extension not in IMAGE_EXTENSIONS or not PHOTO_ID_PATTERN.fullmatch(photo_id)
                or path.is_symlink() or not path.is_file()):
            continue
        preferred = found.get(photo_id)
        if preferred is None or (IMAGE_EXTENSIONS.index(extension), path.name) < (
                IMAGE_EXTENSIONS.index(preferred.suffix.lower()), preferred.name):
            found[photo_id] = path
    return found


def _matches_saved_photo_id(inputs, saved_values):
    """Compare the effective builder prompt with the saved Photo ID fields."""
    if not isinstance(inputs, dict) or not isinstance(saved_values, dict):
        return False
    current = {}
    for field in FIELDS:
        value = inputs.get(field, '')
        if isinstance(value, list) and len(value) == 2:
            continue
        if not isinstance(value, str):
            return False
        if value.strip():
            current[field] = value.strip()
    return current == saved_values


def _upstream_ids(prompt, node_id, saved_photo_ids):
    """Find matching saved Photo IDs that feed this image output node."""
    found, pending, visited = set(), [str(node_id)], set()
    while pending:
        current = pending.pop()
        if current in visited:
            continue
        visited.add(current)
        node = prompt.get(current, {})
        if node.get('class_type') == 'MagichanLab_Krea2PhotoPromptBuilder':
            inputs = node.get('inputs', {})
            photo_id = inputs.get('photo_id') if isinstance(inputs, dict) else None
            if (isinstance(photo_id, str) and PHOTO_ID_PATTERN.fullmatch(photo_id)
                    and not any(character in photo_id for character in '/\\:*?"<>|')
                    and _matches_saved_photo_id(inputs, saved_photo_ids.get(photo_id))):
                found.add(photo_id)
        for value in node.get('inputs', {}).values():
            if isinstance(value, list) and len(value) == 2 and str(value[0]) in prompt:
                pending.append(str(value[0]))
    return found


def _source_image(info, folder_paths):
    if not isinstance(info, dict) or info.get('type') not in ('output', 'temp'):
        return None
    filename, subfolder = info.get('filename'), info.get('subfolder', '')
    if not isinstance(filename, str) or not filename or not isinstance(subfolder, str):
        return None
    root = Path(folder_paths.get_directory_by_type(info['type'])).resolve()
    path = (root / subfolder / filename).resolve()
    if (os.path.commonpath((root, path)) != str(root) or not path.is_file()
            or path.suffix.lower() not in IMAGE_EXTENSIONS):
        return None
    return path


def save_generated_thumbnails(history_item, saved_photo_ids, folder_paths):
    """Save the first output image per linked Photo ID with matching saved fields."""
    from PIL import Image, ImageOps

    prompt_record = history_item.get('prompt', ())
    if len(prompt_record) < 3 or not isinstance(prompt_record[2], dict):
        return []
    prompt = prompt_record[2]
    outputs = history_item.get('outputs', {})
    saved = []
    for node_id, output in outputs.items():
        ids = _upstream_ids(prompt, node_id, saved_photo_ids)
        if not ids or not isinstance(output, dict):
            continue
        for info in output.get('images', []):
            source = _source_image(info, folder_paths)
            if source is None:
                continue
            for photo_id in sorted(ids - set(saved)):
                IMAGE_DIR.mkdir(parents=True, exist_ok=True)
                target = IMAGE_DIR / f'{photo_id}.png'
                temporary = IMAGE_DIR / f'.{photo_id}.{uuid4().hex}.tmp'
                try:
                    with Image.open(source) as original:
                        thumbnail = ImageOps.exif_transpose(original)
                        thumbnail.thumbnail(THUMBNAIL_SIZE, Image.LANCZOS)
                        thumbnail.convert('RGB').save(temporary, format='PNG')
                    temporary.replace(target)
                finally:
                    temporary.unlink(missing_ok=True)
                saved.append(photo_id)
            break
    return saved
