import datetime
import secrets

import bcrypt
from quart import Quart, render_template, request, Response, redirect, url_for, make_response, abort

from checkers import is_authorized
from constants import PATHS_WITHOUT_LOGIN
from decorators import login_required
from exceptions import ObjectNotFound
from middleware import security_middleware, login_middleware, csrf_middleware, session_middleware, \
    form_protection_middleware
from site_variables import db
from database import ObjectDoesNotExist

app = Quart(__name__)


@app.before_serving
async def on_startup():
    await db.create_connection_pool()


@app.after_serving
async def on_shutdown():
    await db.close_all_connections()


@app.route('/')
async def index():
    template_args = {}
    if await is_authorized(request):
        username = request.cookies['username']
        user_color = await db.get(table='user', columns=['sign_color'], condition=f'name="{username}"')
        username_first_letter = username[0].upper()
        template_args['is_authorized'] = True
        template_args['username'] = username
        template_args['user_color'] = user_color
        template_args['first_letter'] = username_first_letter
    return await render_template('index.html', **template_args)


@app.route('/login')
async def login():
    return await render_template('login.html')


@app.route('/login', methods=['POST'])
async def login_post():
    form = await request.form
    template_args = {}
    template_name = f'{request.path.replace("/", "")}.html'
    next_page = request.args.get('next')
    username = form.get('username')
    password = form.get('password')
    remember_password_form = form.get('remember_password')
    remember_password = False if remember_password_form is None else remember_password_form

    async def check_is_none(obj, error_text):
        if obj is None:
            template_args[f'{obj}_state'] = 'wrong'
            template_args[f'{obj}_error'] = error_text
            raise ValueError

    try:
        await check_is_none(username, 'Укажите имя пользователя')
        await check_is_none(password, 'Укажите пароль пользователя')
    except ValueError:
        return await render_template(template_name, **template_args)

    # if username is None:
    #     template_args['username_is_correct'] = False
    #     template_args['username_error'] = 'Укажите имя пользователя'
    #     return await render_template(f'{request.path.replace("/", "")}.html', **template_args)
    # if password is None:
    #     template_args['password_is_correct'] = False
    #     template_args['password_error'] = 'Укажите пароль пользователя'
    try:
        user_password_hash = await db.get(table='user', columns=['password'], condition=f'name="{username}"')
    except ObjectDoesNotExist:
        template_args['username_state'] = 'wrong'
        template_args['username_error'] = f'Пользователя "{username}" не существует'
        return await render_template(template_name, **template_args)

    if bcrypt.checkpw(password.encode('utf-8'), user_password_hash.encode('utf-8')):
        response = await make_response(redirect('/' if next_page is None else next_page))
        if remember_password:
            expire_date = datetime.datetime.now() + datetime.timedelta(days=30)
        else:
            expire_date = None
        response.set_cookie('username', username, expires=expire_date)
        response.set_cookie('password', bcrypt.hashpw(user_password_hash.encode('utf-8'), bcrypt.gensalt()).decode('utf-8'),
                            expires=expire_date)
        return response
    else:
        template_args['password_state'] = 'wrong'
        template_args['password_error'] = f'Неверный пароль пользователя "{username}"'
        return await render_template(template_name, **template_args)


@app.route('/user')
async def user():
    username = request.args.get('name')
    template_args = {}
    if username is None:
        abort(404)

    try:
        creation_date, last_visit, rating, \
        user_color, description, privilege = await db.get(table='user',
                                                          columns=['creation_date', 'last_visit', 'rating',
                                                                   'sign_color', 'description', 'codename'],
                                                          condition=f'name="{username}"',
                                                          join_tables=['privilege'],
                                                          join_conditions=['user.privilege=privilege.id'])
    except ObjectDoesNotExist:
        raise ObjectNotFound(obj=username, obj_name='Пользователя')

    username_first_letter = username[0].upper()
    template_args['username'] = username
    template_args['creation_date'] = creation_date
    template_args['last_visit'] = last_visit
    template_args['rating'] = rating
    template_args['user_color'] = user_color
    template_args['description'] = description
    template_args['privilege'] = privilege
    template_args['first_letter'] = username_first_letter
    print(template_args)
    return await render_template('user.html', **template_args)


@app.errorhandler(404)
async def not_found(e):
    return await render_template('404.html')


@app.errorhandler(ObjectNotFound)
async def obj_not_found(error):
    return await render_template('460.html', obj_name=error.obj_name, obj=error.obj)


@app.before_request
async def before_request():
    response = await form_protection_middleware(request)
    return response


@app.after_request
async def after_request(response: Response):
    response = await session_middleware(request, response)
    response = await login_middleware(request, response)
    response = await csrf_middleware(request, response)
    response = await security_middleware(response)
    return response


@app.context_processor
def context():
    cookies = request.cookies
    cookies_csrf_token = cookies.get('csrf_token').encode('utf-8')
    js_nonce = secrets.token_hex(16)
    css_nonce = secrets.token_hex(16)
    csrf_token = bcrypt.hashpw(cookies_csrf_token, bcrypt.gensalt()).decode('utf-8')

    return {'js_nonce': js_nonce, 'css_nonce': css_nonce, 'csrf_token': csrf_token}


if __name__ == '__main__':
    app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 1
    app.run()
