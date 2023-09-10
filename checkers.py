import bcrypt

from database import ObjectDoesNotExist
from site_variables import db


async def is_authorized(request):
    cookies = request.cookies
    username = cookies.get('username')
    password_hashed_hash = cookies.get('password')

    if (username is None) or (password_hashed_hash is None):
        return False

    try:
        user_password_hash = await db.get(table='user', columns=['password'], condition=f'name="{username}"')
    except ObjectDoesNotExist:
        return False

    return bcrypt.checkpw(user_password_hash.encode('utf-8'), password_hashed_hash.encode('utf-8'))