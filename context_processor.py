import bcrypt

from site_variables import lang_db


def csrf_context_processor(request):
    cookies = request.cookies
    cookies_csrf_token = cookies.get('csrf_token').encode('utf-8')
    return bcrypt.hashpw(cookies_csrf_token, bcrypt.gensalt()).decode('utf-8')


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
