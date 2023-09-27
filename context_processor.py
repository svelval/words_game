from site_variables import lang_db


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
