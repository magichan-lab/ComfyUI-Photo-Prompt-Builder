"""Read-only lookup of local example images for saved Photo IDs."""
from pathlib import Path

from .history import PHOTO_ID_PATTERN

IMAGE_DIR = Path(__file__).resolve().parent / 'data' / 'images'
IMAGE_EXTENSIONS = ('.png', '.jpg', '.jpeg', '.webp', '.gif')


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
