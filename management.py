import os.path
import re
from importlib import import_module

from mysql.connector import pooling

from app_settings import app
from settings import DATABASES_INFO


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


def file_extension(filename: str):
    return filename.lower().split('.')[-1]


def blueprint_migrations_info(blueprint_name):
    try:
        blueprint_migrations_folder = os.path.join(blueprint_name, import_module(f'{blueprint_name}.settings').MIGRATIONS_FOLDER)
    except (ModuleNotFoundError, AttributeError):
        blueprint_migrations_folder = os.path.join(blueprint_name, 'migrations')

    try:
        migrations_folder = os.listdir(blueprint_migrations_folder)
        migrations_dbs_folders = [filename for filename in migrations_folder
                                 if os.path.isdir(os.path.join(blueprint_migrations_folder, filename)) and
                                 filename in DATABASES_INFO
                                 ]
        migrations_path = os.path.join(blueprint_migrations_folder, migrations_folder)
        return {
            'migrations_folder': migrations_folder,
            'migrations': {db_folder: [os.path.join(migrations_path, db_folder, filename) for filename in
                                       os.listdir(os.path.join(migrations_path, db_folder))
                                       if file_extension(filename) == 'sql']
                           for db_folder in migrations_dbs_folders}
        }
    except FileNotFoundError:
        return {}


def make_migrations():
    created_tables_info = {}
    migrations_folders = []
    blueprints_names = [blueprint.import_name.split('.')[0] for blueprint in app.blueprints.values()]
    for blueprint_name in blueprints_names:
        migrations_folder_path = os.path.join(blueprint_name, 'migrations')
        try:
            migrations_db_folders = [filename for filename in os.listdir(migrations_folder_path)
                                     if os.path.isdir(os.path.join(migrations_folder_path, filename)) and
                                     filename in DATABASES_INFO] # TODO: сделать тут DATABASES_INFO из файла настроек текущего блюпринта
            migrations_folders.append(migrations_db_folders)
            for migration_db_folder in migrations_db_folders:
                migrations_db_folder_path = os.path.join(migrations_folder_path, migration_db_folder)
                migrations_files = [filename for filename in os.listdir(migrations_db_folder_path)
                                    if file_extension(filename) in ['sql', 'py']]
                for migration in migrations_files:
                    with open(os.path.join(migrations_db_folder_path, migration), 'r') as data:
                        migration_data = data.read()
                    migration_tables_creations = re.findall('create table .* \(.*\);', migration_data.lower())
                    for table_creation_info in migration_tables_creations:
                        table_creation_info_split = table_creation_info.split(' ')
                        table_name = table_creation_info_split[2].replace('`', '').replace('\'', '').replace('"', '')
                        table_info_without_keys = re.sub('((foreign)|(primary) key).*', '', table_creation_info)
                        only_column_defs = re.sub('create table \S*\s*\(', '', table_info_without_keys)
                        table_columns_info = re.split(',\s*', only_column_defs)
                        if table_name not in created_tables_info:
                            created_tables_info[table_name] = {
                                'create': [],
                                'alter': [],
                            }
                        created_tables_info[table_name]['create'].append({
                            'blueprint': blueprint_name,
                            'db': DATABASES_INFO[migration_db_folder]['name'], # TODO: сделать тут DATABASES_INFO из файла настроек текущего блюпринта
                            'db_folder': migration_db_folder,
                            'migration': migration,
                            'columns': [columns_info_entities.split(' ')[0] for columns_info_entities in table_columns_info]
                        })
        except FileNotFoundError:
            blueprints_names.remove(blueprint_name)
            continue

    for blueprint_name, blueprint_migrations_folders in zip(blueprints_names, migrations_folders):
        print('Making migrations for blueprint ' + CMDStyle.yellow + blueprint_name + CMDStyle.reset + '...')
        for migrations_folder in blueprint_migrations_folders:
            print('\tIn folder ' + CMDStyle.yellow + migrations_folder + CMDStyle.reset + '...')
            migrations_folder_path = os.path.join(blueprint_name, migrations_folder)
            migrations_files = [filename for filename in os.listdir(migrations_folder_path)
                                if file_extension(filename) == 'sql']
            for i, migration in enumerate(migrations_files):
                print(f'\t\t{i+1}. From file ' + CMDStyle.yellow + migration + CMDStyle.reset + '...')
                print(f'\t\t\tCurrent operation: making dependencies for foreign keys...')
                migration_path = os.path.join(migrations_folder_path, migration)
                migration_warnings = []
                migration_dependencies = []
                with open(migration_path, 'r') as data:
                    migration_data = data.read()
                foreign_keys = re.findall('foreign key \(.*\) references .*', migration_data.lower())
                foreign_keys_split = [foreign_key.split() for foreign_key in foreign_keys]
                for foreign_key_info in foreign_keys_split:
                    foreign_key_column = foreign_key_info[2]
                    related_table = foreign_key_info[4]
                    related_table_split = related_table.split('.')
                    related_table_column = foreign_key_info[5].split(')')[0].replace('(','')
                    related_table = related_table_split[-1]
                    related_table_db = DATABASES_INFO[migrations_folder]['name'] # TODO: тут тоже надо брать DATABASES_INFO из настроек блюпринта
                    if len(related_table_split) == 2:
                        related_table_db = related_table_split[0]
                    if related_table not in created_tables_info:
                        migration_warnings.append(f'Related table "{related_table_db}.{related_table}" of foreign key '
                                                  f'"{foreign_key_column}" is not created/altered in any migration')
                        continue

                    related_table_db_found = False
                    related_table_column_found = False
                    related_table_modify_info = created_tables_info[related_table]
                    related_table_creations = related_table_modify_info['create']
                    for related_table_creation in related_table_creations:
                        if related_table_db == related_table_creation['db']:
                            related_table_db_found = True
                            if related_table_column in related_table_creation['columns']:
                                related_table_column_found = True
                                related_migration_blueprint = related_table_creation['blueprint']
                                related_migration_db_folder = related_table_creation['db_folder']
                                related_migration_filename = related_table_creation['migration']
                                related_migration_filename = related_migration_filename[:-len(file_extension(related_migration_filename))] + 'py'
                                break
                    if not related_table_db_found:
                        migration_warnings.append(f'Related table "{related_table_db}.{related_table}" of foreign key '
                                                  f'"{foreign_key_column}" is not created/altered in any migration')
                    elif not related_table_column_found:
                        migration_warnings.append(f'Related table "{related_table_db}.{related_table}" of foreign key '
                                                  f'"{foreign_key_column}" creation/modification found, but it does not have '
                                                  f'column "{related_table_column}"')
                    else:
                        migration_dependencies.append(f'{related_migration_blueprint}.{related_migration_db_folder}.{related_migration_filename}')
                print(f'\t\t\t\t' WARNINGS)
                print(f'\t\t\tCurrent operation: making dependencies for alter tables...')
                # TODO: то же самое, только с ALTER_TABLE
                if migration_dependencies:
                    migration_dependencies_in_file = re.sub('[()]', '', str(migration_dependencies).replace(" ", "\n\t"))
                    migration_dependencies_in_file = f'[\n\t{migration_dependencies_in_file}\n]'
                else:
                    migration_dependencies_in_file = '[]'
                with open(migration_path[:-3] + 'py', 'w') as new_migration:
                    new_migration.write(f'dependencies = {migration_dependencies_in_file}\n\noperations = \'{migration_data}\'')
                    print(f'\t\tMigration file ' + CMDStyle.yellow + new_migration.name + CMDStyle.reset + ' CREATED')


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
