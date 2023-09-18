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

from checkers import is_authorized
from constants import PATHS_WITHOUT_LOGIN
from quart import redirect, url_for, make_response, abort

from cookies import get_or_create_cookie, get_cookie, set_cookie
from site_variables import db


async def security_middleware(response):
    response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'"
    return response


async def session_middleware(request, response):
    if get_cookie(request=request, key='session') is not None:
        new_session_key = secrets.token_hex(32)
        set_cookie(response=response, key='session', value=new_session_key)
        await db.create(table='session', columns=['session_key'], values=[new_session_key])
    return response


async def login_middleware(request, response):
    if (request.path not in PATHS_WITHOUT_LOGIN) and (re.search('(\.css$)|(\.js$)|(\.ico$)|(\.jpg$)', request.path)) is None:
        if not await is_authorized(request):
            result_response = await make_response(redirect(url_for('login', next=request.path)))
            result_response.headers = response.headers
        else:
            return response
    else:
        return response


async def csrf_middleware(request, response):
    get_or_create_cookie(request=request, key='csrf_token', value=secrets.token_hex(32), response=response)
    return response


async def form_protection_middleware(request):
    if request.form is not None:
        form_csrf_token = request.form.get('csrf_token')
        cookies_csrf_token = request.cookies.get('csrf_token').encode('utf-8')
        if not bcrypt.checkpw(cookies_csrf_token, form_csrf_token):
            abort(403, 'CSRF verification failed. Request aborted.')
