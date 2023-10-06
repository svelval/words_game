import datetime

from game.constants import DEFAULT_LANG_CODE
from settings import lang_db


def set_cookie(response, key: str, value: str, expire_date=None):
    if expire_date is None:
        expire_date = datetime.datetime.now() + datetime.timedelta(days=30)
    response.set_cookie(key, value, expires=expire_date)


def get_cookie(request, key: str):
    return request.cookies.get(key)


def get_or_create_cookie(request, key: str, value: str = '', response=None, expire_date=None):
    cookies = request.cookies
    key_cookie = cookies.get(key)
    if key_cookie is None:
        if response is None:
            raise AttributeError('Response cannot be None if you want to set cookie')
        else:
            set_cookie(response=response, key=key, value=value, expire_date=expire_date)
            return value
    else:
        return key_cookie


async def get_or_add_lang_to_cookie(request, lang: str = '', response=None):
    lang_cookie = get_cookie(request, lang)
    if lang_cookie is None:
        set_cookie(response=response, key='lang', value=lang)
        return lang
    else:
        return lang if lang in await lang_db.get_all_lang_codes() else DEFAULT_LANG_CODE
