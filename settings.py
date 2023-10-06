import os

from game.database import CommonDatabase, LanguagesDatabase

common_db_name = os.getenv('WORDS_GAME_DB_NAME', '')
db_user = os.getenv('DB_USER', '')
db_password = os.getenv('DB_PASSWORD', '')

db = CommonDatabase(common_db_name, user=db_user, password=db_password)
lang_db = LanguagesDatabase(related_common_db=common_db_name, user=db_user, password=db_password)


