import secrets

import bcrypt

from settings import db, lang_db


def csrf_context_processor(request):
    cookies = request.cookies
    cookies_csrf_token = cookies.get('csrf_token').encode('utf-8')
    return bcrypt.hashpw(cookies_csrf_token, bcrypt.gensalt()).decode('utf-8')


def nonce_context_processor():
    script_nonce = secrets.token_hex(16)
    style_nonce = secrets.token_hex(16)
    return {'script': script_nonce, 'style': style_nonce}


async def user_data_context_processor(request, request_vars):
    if request_vars.is_authorized:
        if request_vars.get('user_data') is None:
            user_data = {}
            username = request.cookies['username']
            user_color = await db.get(table='user', columns=['sign_color'], condition=f'name="{username}"')
            username_first_letter = username[0].upper()
            user_data['username'] = username
            user_data['user_color'] = user_color
            user_data['first_letter'] = username_first_letter
            return user_data
        else:
            return request_vars.user_data


async def languages_context_processor(request_vars):
    base_text_content = {
        'info_texts': ['language'],
        'button_texts': ['logout'],
    }
    current_text_content = request_vars.text_content
    dict_for_adding = {text_content_type:
                           current_text_content[text_content_type] + base_text_content[text_content_type]
                                if text_content_type in current_text_content else base_text_content[text_content_type]
                       for text_content_type in base_text_content}
    current_text_content.update(dict_for_adding)
    return await lang_db.get_text_content(dict_of_codenames=current_text_content, lang_code=request_vars.lang)
