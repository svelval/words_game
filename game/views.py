import datetime

import bcrypt
from quart import render_template, request, make_response, redirect, abort, g

from game.database_exceptions import ObjectDoesNotExist
from game.exceptions import ObjectNotFound
from settings import db


async def index():
    g.text_content = {'button_texts': ['new_game', 'join_game', 'rating', 'sign_in', 'sign_up']}
    return await render_template('index.html')


async def login():
    return await render_template('login.html')


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
    return await render_template('user.html', **template_args)