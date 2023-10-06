import os

from game.database import CommonDatabase, LanguagesDatabase

common_db_name = os.getenv('WORDS_GAME_DB_NAME', '')
db = CommonDatabase(common_db_name)
lang_db = LanguagesDatabase(related_common_db=common_db_name)


