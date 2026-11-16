"""Same-origin local ComfyUI server endpoints for the frontend extension."""
from aiohttp import web
from server import PromptServer
from .history import FIELDS, MAX_TEXT_LENGTH, add_entries, clear_field, delete_entry, read_history

routes = PromptServer.instance.routes


def _error(exc):
    if isinstance(exc, (ValueError, TypeError)):
        return web.json_response({'error': str(exc)}, status=400)
    return web.json_response({'error': str(exc)}, status=500)


@routes.get('/magichanlab_photo_prompt/history')
async def get_history(request):
    try:
        return web.json_response({'history': read_history()})
    except (OSError, ValueError, RuntimeError) as exc:
        return _error(exc)


@routes.post('/magichanlab_photo_prompt/history')
async def post_history(request):
    try:
        body = await request.json()
        if not isinstance(body, dict):
            raise ValueError('Request must be an object')
        return web.json_response({'history': add_entries(body.get('entries', {}), body.get('limit', 100))})
    except (ValueError, TypeError, OSError, RuntimeError, web.HTTPBadRequest) as exc:
        return _error(exc)


@routes.post('/magichanlab_photo_prompt/history/delete')
async def post_delete(request):
    try:
        body = await request.json()
        if not isinstance(body, dict):
            raise ValueError('Request must be an object')
        return web.json_response({'history': delete_entry(body.get('field'), body.get('value'))})
    except (ValueError, TypeError, OSError, RuntimeError, web.HTTPBadRequest) as exc:
        return _error(exc)


@routes.post('/magichanlab_photo_prompt/history/clear')
async def post_clear(request):
    try:
        body = await request.json()
        if not isinstance(body, dict):
            raise ValueError('Request must be an object')
        return web.json_response({'history': clear_field(body.get('field'))})
    except (ValueError, TypeError, OSError, RuntimeError, web.HTTPBadRequest) as exc:
        return _error(exc)
