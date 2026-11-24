"""ComfyUI endpoints for the frontend and JSON backup commands."""
import asyncio
from functools import partial

from aiohttp import web
from server import PromptServer
from .history import (PhotoIdConflict, add_entries, clear_field, delete_entry,
                      delete_photo_id, export_data, import_data, list_photo_ids,
                      read_history_page, read_photo_id, read_photo_ids, read_state,
                      rename_photo_id)
from .images import photo_images, save_generated_thumbnails

routes = PromptServer.instance.routes


async def _run(function, *args, **kwargs):
    # SQLite lock waits and disk I/O must not block ComfyUI's event loop.
    return await asyncio.get_running_loop().run_in_executor(None, partial(function, *args, **kwargs))


def _error(exc):
    if isinstance(exc, (ValueError, TypeError)):
        return web.json_response({'error': str(exc)}, status=400)
    return web.json_response({'error': str(exc)}, status=500)


@routes.get('/magichanlab_photo_prompt/history')
async def get_history(request):
    try:
        field = request.query.get('field')
        if field is not None:
            before = request.query.get('before')
            return web.json_response(await _run(
                read_history_page, field, None if before is None else int(before),
                int(request.query.get('page_size', '100'))))
        return web.json_response(await _run(
            read_state, include_history=request.query.get('include_history') != '0'))
    except (OSError, ValueError, RuntimeError) as exc:
        return _error(exc)


@routes.get('/magichanlab_photo_prompt/photo_id/images')
async def get_photo_images(request):
    try:
        saved_ids = set(await _run(list_photo_ids))
        images = {photo_id: path.stat().st_mtime_ns
                  for photo_id, path in photo_images().items() if photo_id in saved_ids}
        return web.json_response({'images': images}, headers={'Cache-Control': 'no-store'})
    except (OSError, ValueError, RuntimeError) as exc:
        return _error(exc)


@routes.get('/magichanlab_photo_prompt/photo_id/image')
async def get_photo_image(request):
    photo_id = request.query.get('photo_id', '')
    try:
        if await _run(read_photo_id, photo_id) is None:
            raise web.HTTPNotFound()
        path = photo_images().get(photo_id)
        if path is None:
            raise web.HTTPNotFound()
        return web.FileResponse(path, headers={'Cache-Control': 'no-store'})
    except (OSError, ValueError, RuntimeError) as exc:
        return _error(exc)


@routes.post('/magichanlab_photo_prompt/photo_id/generation_thumbnail')
async def post_generation_thumbnail(request):
    try:
        body = await request.json()
        prompt_id = body.get('prompt_id') if isinstance(body, dict) else None
        if not isinstance(prompt_id, str) or not prompt_id:
            raise ValueError('prompt_id is required')
        history = PromptServer.instance.prompt_queue.get_history(prompt_id=prompt_id)
        if prompt_id not in history:
            return web.json_response({'pending': True}, status=202)
        import folder_paths
        saved_photo_ids = await _run(read_photo_ids)
        saved = await _run(save_generated_thumbnails, history[prompt_id], saved_photo_ids, folder_paths)
        return web.json_response({'saved_photo_ids': saved})
    except (OSError, ValueError, TypeError, RuntimeError, web.HTTPBadRequest) as exc:
        return _error(exc)


@routes.get('/magichanlab_photo_prompt/history/export')
async def get_history_export(request):
    try:
        return web.json_response(await _run(export_data), headers={
            'Content-Disposition': 'attachment; filename="photo-prompt-history.json"',
        })
    except (OSError, ValueError, RuntimeError) as exc:
        return _error(exc)


@routes.post('/magichanlab_photo_prompt/history/import')
async def post_history_import(request):
    try:
        return web.json_response(await _run(import_data, await request.json()))
    except (OSError, ValueError, RuntimeError, web.HTTPBadRequest) as exc:
        return _error(exc)


@routes.post('/magichanlab_photo_prompt/history')
async def post_history(request):
    try:
        body = await request.json()
        if not isinstance(body, dict):
            raise ValueError('Request must be an object')
        return web.json_response(await _run(add_entries, body.get('entries', {}),
                                           body.get('photo_id'), body.get('enabled'),
                                           body.get('overwrite', False), include_history=False))
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
        return web.json_response(await _run(delete_entry, body.get('field'), body.get('value'), include_history=False))
    except (ValueError, TypeError, OSError, RuntimeError, web.HTTPBadRequest) as exc:
        return _error(exc)


@routes.post('/magichanlab_photo_prompt/history/clear')
async def post_clear(request):
    try:
        body = await request.json()
        if not isinstance(body, dict):
            raise ValueError('Request must be an object')
        return web.json_response(await _run(clear_field, body.get('field'), include_history=False))
    except (ValueError, TypeError, OSError, RuntimeError, web.HTTPBadRequest) as exc:
        return _error(exc)


@routes.post('/magichanlab_photo_prompt/photo_id/rename')
async def post_rename_photo_id(request):
    try:
        body = await request.json()
        if not isinstance(body, dict):
            raise ValueError('Request must be an object')
        return web.json_response(await _run(rename_photo_id, body.get('old_id'), body.get('new_id'), include_history=False))
    except (ValueError, TypeError, OSError, RuntimeError, web.HTTPBadRequest) as exc:
        return _error(exc)


@routes.post('/magichanlab_photo_prompt/photo_id/delete')
async def post_delete_photo_id(request):
    try:
        body = await request.json()
        if not isinstance(body, dict):
            raise ValueError('Request must be an object')
        return web.json_response(await _run(delete_photo_id, body.get('photo_id'), include_history=False))
    except (ValueError, TypeError, OSError, RuntimeError, web.HTTPBadRequest) as exc:
        return _error(exc)
