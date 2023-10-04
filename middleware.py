# from werkzeug.datastructures import Headers
#
# from hypercorn.asyncio import lifespan
#
#
# class SecurityMiddleware:
#     def __init__(self, app):
#         self.app = app
#
#     async def __call__(self, scope, receive, send):
#         # response_type = scope.get('type')
#         # response_headers = scope.get('headers')
#         # scope['type'] = 'http.response.start'
#         if 'headers' in scope:
#             new_headers = scope['headers'] + [
#                     (b'Strict-Transport-Security', b'max-age=31536000; includeSubDomains'),
#                     (b'Content-Security-Policy', b"default-src 'self'; script-src 'self'")
#                 ]
#             scope['headers'] = new_headers  # Headers(new_headers)
#         print(await self.app(scope, receive, send))
#         return await self.app(scope, receive, send)
import re
import secrets

import bcrypt

from constants import PATHS_WITHOUT_LOGIN, DEFAULT_LANG_CODE
from quart import redirect, url_for, make_response, abort

from cookies import get_or_create_cookie, get_cookie, set_cookie
from database_exceptions import ObjectDoesNotExist
from site_variables import db, lang_db


async def security_middleware(response, **kwargs):
    headers = "default-src 'self';"
    for setting_name in kwargs:
        headers += f"{setting_name}-src 'self' 'nonce-{kwargs[setting_name]}';"

    headers += f"img-src 'self'"
    response.headers['Content-Security-Policy'] = headers
    return response


async def session_middleware(request, response):
    if get_cookie(request=request, key='session') is not None:
        new_session_key = secrets.token_hex(32)
        set_cookie(response=response, key='session', value=new_session_key)
        await db.create(table='session', columns=['session_key'], values=[new_session_key])
    return response


async def path_is_file_middleware(request, request_vars):
    request_vars.path_is_file = (re.search('(\.css$)|(\.js$)|(\.ico$)|(\.jpg$)|(\.png$)', request.path) is not None)


async def login_middleware(request, request_vars):
    if not request_vars.path_is_file:
        cookies = request.cookies
        username = cookies.get('username')
        password_hashed_hash = cookies.get('password')

        if (username is None) or (password_hashed_hash is None):
            request_vars.is_authorized = False
        else:
            try:
                user_password_hash = await db.get(table='user', columns=['password'], condition=f'name="{username}"')
                request_vars.is_authorized = bcrypt.checkpw(user_password_hash.encode('utf-8'),
                                                            password_hashed_hash.encode('utf-8'))
            except ObjectDoesNotExist:
                request_vars.is_authorized = False
    else:
        request_vars.is_authorized = None


async def login_required_middleware(request, request_vars):
    if (request.path not in PATHS_WITHOUT_LOGIN) and (not request_vars.path_is_file) and (not request_vars.is_authorized):
        result_response = await make_response(redirect(url_for('login', next=request.path)))
        return result_response


async def csrf_middleware(request, response):
    get_or_create_cookie(request=request, key='csrf_token', value=secrets.token_hex(32), response=response)
    return response


async def form_protection_middleware(request):
    request_form = await request.form
    if len(request_form) != 0:
        form_csrf_token = request_form.get('csrf_token').encode('utf-8')
        cookies_csrf_token = request.cookies.get('csrf_token').encode('utf-8')
        if (form_csrf_token is None) or (not bcrypt.checkpw(cookies_csrf_token, form_csrf_token)):
            abort(403, 'CSRF verification failed. Request aborted.')


async def languages_middleware(request, request_vars):
    if 'all_langs' not in request_vars:
        request_vars.all_langs = await lang_db.get_all_langs()
    lang_from_cookies = get_cookie(request, 'lang')
    if lang_from_cookies is None:
        request_vars.lang = DEFAULT_LANG_CODE
    else:
        request_vars.lang = lang_from_cookies if lang_from_cookies in request_vars.all_langs.keys() else DEFAULT_LANG_CODE
    request_vars.text_content = {}


async def detect_language_middleware(request_vars, response):
    set_cookie(response=response, key='lang', value=request_vars.lang)


def nonce_middleware(request_vars):
    request_vars.nonces = {}
