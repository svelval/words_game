from quart import request, redirect, url_for

from site_variables import db


async def login_required(route):
    print('hhhhh')
    async def wrapper(*args, **kwargs):
        cookies = request.cookies
        username = cookies.get('name')
        password_hash = cookies.get('password')
        if (username is None) or (password_hash is None):
            print(redirect(url_for('main.login')))
            return
        if len(await db.filter(table='user', condition=f'name={username} AND password={password_hash}')) == 0:
            redirect(url_for('main.login'))
            return
        else:
            await route(args, kwargs)
    return wrapper
