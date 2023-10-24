import os

from game.database import CommonDatabase, LanguagesDatabase


DATABASES_INFO = {
    'common': {
        'name': os.getenv('WORDS_GAME_DB_NAME', ''),
        'user': os.getenv('DB_USER'),
        'password': os.getenv('DB_PASSWORD', '')
    },
    'langs': {
        'name': os.getenv('WORDS_GAME_LANGS_DB_NAME', ''),
        'user': os.getenv('DB_USER'),
        'password': os.getenv('DB_PASSWORD', '')
    },
    'default': 'common',
}
MIGRATIONS_TABLE_INFO = DATABASES_INFO['common']

db = CommonDatabase(DATABASES_INFO['common']['name'],
                    user=DATABASES_INFO['common']['user'],
                    password=DATABASES_INFO['common']['password'])
lang_db = LanguagesDatabase(lang_db=DATABASES_INFO['langs']['name'],
                            related_common_db=DATABASES_INFO['common']['name'],
                            user=DATABASES_INFO['langs']['user'],
                            password=DATABASES_INFO['langs']['password'])


