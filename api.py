"""Same-origin local ComfyUI server endpoints for the frontend extension."""
from aiohttp import web
from server import PromptServer
from .history import (PhotoIdConflict, add_entries, clear_field, delete_entry,
                      delete_photo_id, read_state, rename_photo_id)

routes = PromptServer.instance.routes


def _error(exc):
    if isinstance(exc, (ValueError, TypeError)):
        return web.json_response({'error': str(exc)}, status=400)
    return web.json_response({'error': str(exc)}, status=500)


@routes.get('/magichanlab_photo_prompt/history')
async def get_history(request):
    try:
        return web.json_response(read_state())
    except (OSError, ValueError, RuntimeError) as exc:
        return _error(exc)


@routes.post('/magichanlab_photo_prompt/history')
async def post_history(request):
    try:
        body = await request.json()
        if not isinstance(body, dict):
            raise ValueError('Request must be an object')
        return web.json_response(add_entries(body.get('entries', {}), body.get('limit', 100),
                                             body.get('photo_id'), body.get('enabled'),
                                             body.get('overwrite', False)))
    except PhotoIdConflict as exc:
        return web.json_response({'error': str(exc), 'photo_id': exc.photo_id,
                                  'conflicts': exc.fields}, status=409)
    except (ValueError, TypeError, OSError, RuntimeError, web.HTTPBadRequest) as exc:
        return _error(exc)


@routes.post('/magichanlab_photo_prompt/history/delete')
async def post_delete(request):
    try:
        body = await request.json()
        if not isinstance(body, dict):
            raise ValueError('Request must be an object')
        return web.json_response(delete_entry(body.get('field'), body.get('value')))
    except (ValueError, TypeError, OSError, RuntimeError, web.HTTPBadRequest) as exc:
        return _error(exc)


@routes.post('/magichanlab_photo_prompt/history/clear')
async def post_clear(request):
    try:
        body = await request.json()
        if not isinstance(body, dict):
            raise ValueError('Request must be an object')
        return web.json_response(clear_field(body.get('field')))
    except (ValueError, TypeError, OSError, RuntimeError, web.HTTPBadRequest) as exc:
        return _error(exc)


@routes.post('/magichanlab_photo_prompt/photo_id/rename')
async def post_rename_photo_id(request):
    try:
        body = await request.json()
        if not isinstance(body, dict):
            raise ValueError('Request must be an object')
        return web.json_response(rename_photo_id(body.get('old_id'), body.get('new_id')))
    except (ValueError, TypeError, OSError, RuntimeError, web.HTTPBadRequest) as exc:
        return _error(exc)


@routes.post('/magichanlab_photo_prompt/photo_id/delete')
async def post_delete_photo_id(request):
    try:
        body = await request.json()
        if not isinstance(body, dict):
            raise ValueError('Request must be an object')
        return web.json_response(delete_photo_id(body.get('photo_id')))
    except (ValueError, TypeError, OSError, RuntimeError, web.HTTPBadRequest) as exc:
        return _error(exc)
