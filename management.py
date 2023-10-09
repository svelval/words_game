import os.path
from importlib import import_module

from mysql.connector import pooling

from app_settings import app
from settings import common_db_name, db_user, db_password


class CMDStyle:
    black = '\033[30m'
    red = '\033[31m'
    green = '\033[32m'
    orange = '\033[33m'
    blue = '\033[34m'
    purple = '\033[35m'
    cyan = '\033[36m'
    lightgrey = '\033[37m'
    darkgrey = '\033[90m'
    lightred = '\033[91m'
    lightgreen = '\033[92m'
    yellow = '\033[93m'
    lightblue = '\033[94m'
    pink = '\033[95m'
    lightcyan = '\033[96m'
    reset = '\033[0m'
    bold = '\033[01m'
    disable = '\033[02m'
    underline = '\033[04m'
    reverse = '\033[07m'
    strikethrough = '\033[09m'
    invisible = '\033[08m'


def make_migrations():
    pass


def migrate():
    connection_pool = pooling.MySQLConnectionPool(port=3306,
                                                  database=common_db_name,
                                                  user=db_user,
                                                  password=db_password)
    try:
        with connection_pool.get_connection() as conn:
            with conn.cursor() as cur:
                for blueprint in app.blueprints.values():
                    blueprint_name = blueprint.import_name.split('.')[0]
                    try:
                        blueprint_migrations_folder = os.path.join(blueprint_name,
                                                                   import_module(f'{blueprint_name}.settings').MIGRATIONS_FOLDER)
                    except (ModuleNotFoundError, AttributeError):
                        blueprint_migrations_folder = os.path.join(blueprint_name, 'migrations')

                    try:
                        migrations = os.listdir(blueprint_migrations_folder)
                    except FileNotFoundError:
                        print(CMDStyle.red + f'Migrations directory "{blueprint_migrations_folder}" ({blueprint_name}) does not exist' + CMDStyle.reset)
                        continue

                    print('Applying migrations in ' + CMDStyle.yellow + f'{blueprint_name}' + CMDStyle.reset + ' blueprint...')
                    for i, migration in enumerate(migrations):
                        if migration.split('.')[-1].lower() == 'sql':
                            print(f'\t{i+1}. ', end='')
                            migration_path = os.path.join(blueprint_migrations_folder, migration)
                            with open(migration_path, 'r') as file:
                                migration_data = file.read()

                            try:
                                cur.execute(migration_data)
                                conn.commit()
                                print(CMDStyle.green + f'Migration "{migration}" applied' + CMDStyle.reset)
                            except Exception as error:
                                print(CMDStyle.red + f'Error in migration "{migration}": ' + CMDStyle.bold + f'{error}' + CMDStyle.reset)
                                continue
                    print('\n')
    except Exception as ex:
        print(CMDStyle.red + f'Error during migrations applying process: {ex}' + CMDStyle.reset)


def execute_from_command_line(argv):
    try:
        command = argv[1]
    except IndexError:
        return

    try:
        command_args = argv[2:]
    except IndexError:
        command_args = []

    try:
        globals()[command](*command_args)
    except KeyError:
        print(CMDStyle.red + f'Unknown command : {command}' + CMDStyle.reset)
    except TypeError as ex:
        print(CMDStyle.red + f'{ex}' + CMDStyle.reset)
    exit()
