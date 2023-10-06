from quart import g, request, Response
from settings import db, lang_db

from game.context_processor import languages_context_processor, csrf_context_processor, nonce_context_processor, \
    user_data_context_processor, static_files_context_processor
from game.middleware import path_is_file_middleware, login_middleware, login_required_middleware, form_protection_middleware, \
    languages_middleware, nonce_middleware, session_middleware, csrf_middleware, security_middleware, \
    detect_language_middleware


async def on_startup():
    await db.create_connection_pool()
    await lang_db.create_connection_pool()


async def on_shutdown():
    await db.close_all_connections()
    await lang_db.close_all_connections()


async def before_request():
    await path_is_file_middleware(request, g)
    await login_middleware(request, g)
    response = await login_required_middleware(request, g)
    await form_protection_middleware(request)
    await languages_middleware(request, g)

    nonce_middleware(g)
    return response


async def after_request(response: Response):
    response = await session_middleware(request, response)
    response = await csrf_middleware(request, response)
    response = await security_middleware(response, **g.nonces)
    await detect_language_middleware(g, response)
    return response


async def context_processor():
    text_content = await languages_context_processor(request_vars=g)
    csrf_token = csrf_context_processor(request)
    g.nonces = nonce_context_processor()
    g.user_data = await user_data_context_processor(request, g)
    static_function = static_files_context_processor

    return {
        'is_authorized': g.is_authorized, 'csrf_token': csrf_token, 'lang': g.lang, 'all_langs': g.all_langs,
        'text_content': text_content, 'static': static_function, **g.nonces, **g.user_data
    }
