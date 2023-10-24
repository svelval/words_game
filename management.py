import datetime
import os.path
import re
import traceback
from importlib import import_module

from mysql.connector import pooling, ProgrammingError

import settings
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


class Migration:
    def __init__(self):
        self.created_tables_info = {}
        self.db_conn_pools = {}
        self.applied_migrations = []

        blueprints_names = self.get_blueprint_names()
        self.blueprints_db_settings = {}
        for blueprint_name in blueprints_names:
            try:
                self.blueprints_db_settings[blueprint_name] = import_module(f'{blueprint_name}.settings').DATABASES_INFO
            except (ModuleNotFoundError, AttributeError):
                self.blueprints_db_settings[blueprint_name] = DATABASES_INFO
        self.migrations_for_db = []
        self.applied_migrations_db = None

    @staticmethod
    def get_blueprint_names():
        return [blueprint.import_name.split('.')[0] for blueprint in app.blueprints.values()]

    @staticmethod
    def file_extension(filename: str):
        return filename.lower().split('.')[-1]

    @staticmethod
    def __prepare_migration_data(migration_data):
        migration_data = re.sub('\(\s*', '(', migration_data.lower().replace('\n', ''))
        return re.sub('\s*\)', ')', migration_data)

    def __create_migrations_db_table(self):
        try:
            migrations_db_info = settings.MIGRATIONS_TABLE_INFO
        except AttributeError:
            default_db = settings.DATABASES_INFO['default']
            migrations_db_info = settings.DATABASES_INFO[default_db]
        with pooling.MySQLConnection(port=3306, database=migrations_db_info['name'],
                                     user=migrations_db_info['user'], password=migrations_db_info['password']) as conn:
            with conn.cursor() as cur:
                try:
                    for _ in cur.execute('''CREATE TABLE migrations (
                                        id int not null auto_increment primary key,
                                        blueprint varchar(100) not null,
                                        db_name varchar(100) not null,
                                        `name` varchar(150) not null,
                                        applied datetime null,
                                        unique (blueprint, db_name, `name`)
                                   );
    
                                CREATE TRIGGER migrations_onCreate
                                    BEFORE INSERT
                                    ON `migrations` FOR EACH ROW
                                        SET NEW.applied = IFNULL(NEW.applied, NOW());''', multi=True):
                        ...
                    conn.commit()
                except ProgrammingError:
                    pass
        self.applied_migrations_db = migrations_db_info

    def __get_applied_migrations(self):
        try:
            with pooling.MySQLConnection(port=3306, database=self.applied_migrations_db['name'],
                                         user=self.applied_migrations_db['user'], password=self.applied_migrations_db['password']) as conn:
                with conn.cursor() as cur:
                    cur.execute(f'SELECT blueprint, db_name, `name` FROM migrations')
                    return list(cur.fetchall())
        except ProgrammingError:
            raise NameError(CMDStyle.red + 'Cannot get applied migrations: most likely due to incorrect '
                                           'MIGRATIONS_TABLE_INFO in project settings' + CMDStyle.reset)

    def __write_applied_migrations_to_db(self):
        if not self.migrations_for_db:
            return
        with pooling.MySQLConnection(port=3306, database=self.applied_migrations_db['name'],
                                     user=self.applied_migrations_db['user'],
                                     password=self.applied_migrations_db['password']) as conn:
            with conn.cursor() as cur:
                try:
                    cur.execute(f'INSERT INTO migrations (blueprint, db_name, `name`, applied) VALUES '
                                f'{",".join(self.migrations_for_db) + ";"}')
                    conn.commit()
                except ProgrammingError as err:
                    duplicate_row = re.search('\'\S*\'', str(err)).group()
                    raise NameError(CMDStyle.red + f'Migration ' + CMDStyle.yellow + duplicate_row + CMDStyle.red +
                                    ' is already applied' + CMDStyle.reset)

    def __file_is_potential_migration(self, filename, allowed_extensions):
        if isinstance(allowed_extensions, str):
            allowed_extensions = [allowed_extensions]
        return (self.file_extension(filename) in allowed_extensions) and (re.search('^[a-zA-Z_]', filename) is not None)

    def __migration_applying_iteration(self, blueprint_name, migration_db_folder, migration, tabs_count):
        migration_module_path = f'{blueprint_name}.migrations.{migration_db_folder}.{migration}'
        tabs = ''.join(['\t' for _ in range(tabs_count)])
        if (migration_module_path in self.applied_migrations) or \
                ((blueprint_name, migration_db_folder, migration,) in self.earlier_applied_migrations):
            print(tabs + CMDStyle.cyan + f'Migration is already applied' + CMDStyle.reset)
            return
        try:
            migration_module = import_module(f'{blueprint_name}.migrations.{migration_db_folder}.{migration}')
            migration_dependencies = migration_module.dependencies
            migration_operations = migration_module.operations
        except (ModuleNotFoundError, AttributeError):
            print(tabs + CMDStyle.red + f'File ' + CMDStyle.yellow + migration + CMDStyle.red + ' is not a migration' +
                  CMDStyle.reset)
            return

        if migration_dependencies:
            tabs_count += 1
            tabs += '\t'
        for dependency in migration_dependencies:
            print(tabs + 'Current operation: applying dependency migration ' + CMDStyle.yellow + dependency +
                  CMDStyle.reset + '...')
            dependency_split = dependency.split('/')
            blueprt_name = dependency_split[0]
            migr_folder = dependency_split[1]
            migr_name = dependency_split[2]
            self.__migration_applying_iteration(blueprt_name, migr_folder, migr_name, tabs_count)

        if migration_dependencies:
            tabs = tabs.replace('\t', '', 1)
        with self.db_conn_pools[f'{blueprint_name}/{migration_db_folder}'].get_connection() as conn:
            with conn.cursor() as cur:
                try:
                    cur.execute(migration_operations)
                    conn.commit()
                    self.applied_migrations.append(migration_module_path)
                    self.migrations_for_db.append(str((blueprint_name, migration_db_folder,
                                                                       migration, str(datetime.datetime.now()),)))
                    print(tabs + CMDStyle.green + f'Migration ' + CMDStyle.yellow + migration +
                          CMDStyle.green + ' applied' + CMDStyle.reset)
                except Exception as error:
                    print(tabs + CMDStyle.red + f'Error while applying migration ' + CMDStyle.yellow +
                          migration + CMDStyle.red + ': ' + CMDStyle.bold + str(error) + CMDStyle.reset)

    def __make_dependencies(making_fun):
        def inner(self, migration_data, migration_db, dependencies):
            migration_warnings = []
            making_fun(self, migration_data, migration_db, dependencies, migration_warnings)
            if migration_warnings:
                print(CMDStyle.orange + f'\t\t\tWARNINGS:' + '\n\t\t\t\t- '.join(
                    migration_warnings) + CMDStyle.reset)
            migration_warnings.clear()
        return inner

    def search_suitable_table_creation(self, table, table_db, table_cols, warning, migration_dependencies,
                                       migration_warnings):
        if isinstance(table_cols, str):
            table_cols = [table_cols]
        migration_warnings.append(warning)
        try:
            related_table_creations = list(
                map(lambda altering_table_creation_info: altering_table_creation_info
                    if altering_table_creation_info['db'] == table_db and
                    all(table_col in altering_table_creation_info['columns'] for table_col in table_cols) else None,
                    self.created_tables_info[table])
            )
        except KeyError:
            return
        related_table_suitable_creations = [creation for creation in related_table_creations if
                                            creation is not None]
        if related_table_suitable_creations:
            suitable_creation_blueprint = related_table_suitable_creations[0]['blueprint']
            suitable_creation_db_folder = related_table_suitable_creations[0]['db_folder']
            suitable_creation_migration = related_table_suitable_creations[0]['migration']
            dependency = f'{suitable_creation_blueprint}/{suitable_creation_db_folder}/{suitable_creation_migration}'
            if dependency not in migration_dependencies:
                migration_dependencies.append(dependency)
            migration_warnings.remove(warning)

    @__make_dependencies
    def make_foreign_keys_dependencies(self, migration_data, migration_db, dependencies, migration_warnings):
        print(f'\t\t\tCurrent operation: making dependencies for foreign keys...')
        foreign_keys = re.findall('foreign key\s*\S*\s*\(.*\) references .*', migration_data)
        foreign_keys_split = [foreign_key.split() for foreign_key in foreign_keys]
        for foreign_key_info in foreign_keys_split:
            if foreign_key_info[2].find('(') == -1:
                foreign_key_name = foreign_key_info[2]
                del foreign_key_info[2]
            else:
                foreign_key_name = foreign_key_info[2]
            # foreign_key_column = re.sub('[()]', '', foreign_key_info[2])
            related_table = foreign_key_info[4]
            related_table_column = re.sub('[()]', '', foreign_key_info[5])
            related_table_split = related_table.split('.')
            related_table = related_table_split[-1]
            related_table_db = migration_db
            if len(related_table_split) == 2:
                related_table_db = related_table_split[0]

            self.search_suitable_table_creation(related_table, related_table_db, related_table_column,
                                                f'Related table "{related_table_db}.{related_table}" of foreign key '
                                                f'"{foreign_key_name}" is not created in any migration',
                                                dependencies, migration_warnings)

    @__make_dependencies
    def make_alter_table_dependencies(self, migration_data, migration_db, dependencies, migration_warnings):
        print(f'\t\t\tCurrent operation: making dependencies for alter tables...')
        alters_tables = re.findall('alter table .*;?', migration_data)
        for alter_table_str in alters_tables:
            altering_table = alter_table_str.split()[2]
            if altering_table not in self.created_tables_info:
                migration_warnings.append(
                    f'Altering table "{altering_table}" is not created in any migration')
                continue
            alter_table_body = re.sub('alter table (\S)*(\s)*', '', alter_table_str)
            columns_to_edit = [re.split('column\s+', stmt)[-1] for stmt in
                               re.split(',\s*', alter_table_body)
                               if 'column' in stmt]

            self.search_suitable_table_creation(altering_table, migration_db, columns_to_edit,
                                                f'Altering table "{altering_table}" with '
                                                f'columns ({", ".join(columns_to_edit)}) is not created in any migration',
                                                dependencies, migration_warnings)

    def prepare_migration_folders(self):
        for blueprint_name in self.get_blueprint_names():
            migrations_folder_path = os.path.join(blueprint_name, 'migrations')
            try:
                os.mkdir(migrations_folder_path)
            except FileExistsError:
                pass
            for db_folder in self.blueprints_db_settings[blueprint_name]:
                try:
                    os.mkdir(os.path.join(migrations_folder_path, db_folder))
                except FileExistsError:
                    pass

    def make_migrations(self):
        migrations_folders = []
        blueprints_names = self.get_blueprint_names()
        for blueprint_name in blueprints_names:
            migrations_folder_path = os.path.join(blueprint_name, 'migrations')
            try:
                migrations_db_folders = [filename for filename in os.listdir(migrations_folder_path)
                                         if os.path.isdir(os.path.join(migrations_folder_path, filename)) and
                                         filename in self.blueprints_db_settings[blueprint_name]]
                if migrations_db_folders:
                    migrations_folders.append(migrations_db_folders)
                else:
                    blueprints_names.remove(blueprint_name)

                for migration_db_folder in migrations_db_folders:
                    migrations_db_folder_path = os.path.join(migrations_folder_path, migration_db_folder)
                    migrations_files = [filename for filename in os.listdir(migrations_db_folder_path)
                                        if self.__file_is_potential_migration(filename, ['sql', 'py'])]
                    for migration in migrations_files:
                        with open(os.path.join(migrations_db_folder_path, migration), 'r') as data:
                            migration_data = self.__prepare_migration_data(data.read())
                        migration_tables_creations = re.findall('create table\s*\S*\s*\(.*\);?', migration_data)
                        for table_creation_info in migration_tables_creations:
                            table_creation_info_split = table_creation_info.split(' ')
                            table_name = table_creation_info_split[2].replace('`', '').replace('\'', '').replace('"', '')
                            table_info_without_keys = re.sub('((foreign)|(primary) key).*', '', table_creation_info)
                            only_column_defs = re.sub('create table \S*\s*\(', '', table_info_without_keys)
                            table_columns_info = re.split(',\s*', only_column_defs)
                            if table_name not in self.created_tables_info:
                                self.created_tables_info[table_name] = []
                            self.created_tables_info[table_name].append({
                                'blueprint': blueprint_name,
                                'db': self.blueprints_db_settings[blueprint_name][migration_db_folder]['name'],
                                'db_folder': migration_db_folder,
                                'migration': migration,
                                'columns': [columns_info_entities.split(' ')[0] for columns_info_entities in
                                            table_columns_info]
                            })
            except FileNotFoundError:
                blueprints_names.remove(blueprint_name)
                continue

        for blueprint_name, blueprint_migrations_folders in zip(blueprints_names, migrations_folders):
            print('Making migrations for blueprint ' + CMDStyle.yellow + blueprint_name + CMDStyle.reset + '...')
            for migrations_folder in blueprint_migrations_folders:
                migrations_folder_path = os.path.join(blueprint_name, 'migrations', migrations_folder)
                migrations_files = [filename for filename in os.listdir(migrations_folder_path)
                                    if self.__file_is_potential_migration(filename, 'sql')]
                migration_db = self.blueprints_db_settings[blueprint_name][migrations_folder]['name']
                if migrations_files:
                    print('\tIn folder ' + CMDStyle.yellow + migrations_folder + CMDStyle.reset + '...')
                for i, migration in enumerate(migrations_files):
                    print(f'\t\t{i + 1}. From file ' + CMDStyle.yellow + migration + CMDStyle.reset + '...')
                    migration_path = os.path.join(migrations_folder_path, migration)
                    migration_dependencies = []
                    with open(migration_path, 'r') as data:
                        migration_data_original = data.read()
                    migration_data = self.__prepare_migration_data(migration_data_original)

                    self.make_foreign_keys_dependencies(migration_data, migration_db, migration_dependencies)
                    self.make_alter_table_dependencies(migration_data, migration_db, migration_dependencies)

                    # TODO: то же самое, только с ALTER_TABLE
                    if migration_dependencies:
                        migration_dependencies_in_file = re.sub('[\[\]]', '',
                                                                str(migration_dependencies).replace(" ", "\n\t"))
                        migration_dependencies_in_file = f'[\n\t{migration_dependencies_in_file}\n]'
                    else:
                        migration_dependencies_in_file = '[]'
                    with open(migration_path[:-4], 'w') as new_migration:
                        new_migration.write(
                            f'dependencies = {migration_dependencies_in_file}\n\noperations = \'\'\'{migration_data_original}\'\'\'')
                        print(
                            f'\t\t\tMigration file ' + CMDStyle.yellow + new_migration.name + CMDStyle.reset + ' CREATED')

    def migrate(self):
        try:
            self.__create_migrations_db_table()
        except (AttributeError, KeyError, ProgrammingError) as error:
            if isinstance(error, (AttributeError, KeyError)):
                error_msg = 'Database to save migrations is not specified. Check if you set MIGRATIONS_TABLE_INFO ' \
                            'or \'default\' database inside DATABASES_INFO in ' + CMDStyle.yellow + 'settings.py'
            else:
                error_msg = f'Wrong data of migrations database : ' + CMDStyle.bold + str(error)
            print(CMDStyle.red + error_msg + CMDStyle.reset)
            return

        try:
            self.earlier_applied_migrations = self.__get_applied_migrations()
        except NameError as err:
            print(err)
            return

        migrations_folders = []
        blueprints_names = self.get_blueprint_names()
        for blueprint_name in blueprints_names:
            migrations_folder_path = os.path.join(blueprint_name, 'migrations')
            try:
                migrations_db_folders = [filename for filename in os.listdir(migrations_folder_path)
                                         if os.path.isdir(os.path.join(migrations_folder_path, filename)) and
                                         filename in self.blueprints_db_settings[blueprint_name]]
                if migrations_db_folders:
                    migrations_folders.append(migrations_db_folders)
                else:
                    blueprints_names.remove(blueprint_name)
                for migration_db_folder in migrations_db_folders:
                    self.db_conn_pools[f'{blueprint_name}/{migration_db_folder}'] = pooling.MySQLConnectionPool(
                        port=3306,
                        database=self.blueprints_db_settings[blueprint_name][migration_db_folder]['name'],
                        user=self.blueprints_db_settings[blueprint_name][migration_db_folder]['user'],
                        password=self.blueprints_db_settings[blueprint_name][migration_db_folder]['password'])
            except FileNotFoundError:
                blueprints_names.remove(blueprint_name)

        for blueprint_name, migrations_db_folders in zip(blueprints_names, migrations_folders):
            migrations_folder_path = os.path.join(blueprint_name, 'migrations')
            if migrations_db_folders:
                print('Applying migrations of blueprint ' + CMDStyle.yellow + blueprint_name + CMDStyle.reset + '...')
            for migration_db_folder in migrations_db_folders:
                migrations_db_folder_path = os.path.join(migrations_folder_path, migration_db_folder)
                migrations_files = [filename[:-3] for filename in os.listdir(migrations_db_folder_path)
                                    if self.__file_is_potential_migration(filename, 'py')]
                if migrations_files:
                    print('\tIn folder ' + CMDStyle.yellow + migration_db_folder + CMDStyle.reset + '...')
                else:
                    self.db_conn_pools.pop(f'{blueprint_name}/{migration_db_folder}', None)
                for i, migration in enumerate(migrations_files):
                    print(f'\n\t\t{i + 1}. Migration ' + CMDStyle.yellow + migration + CMDStyle.reset + '...')
                    tabs_count = 2
                    self.__migration_applying_iteration(blueprint_name, migration_db_folder, migration, tabs_count)
        try:
            self.__write_applied_migrations_to_db()
        except NameError as err:
            print(err)


def execute_from_command_line(argv):
    try:
        command = argv[1]
    except IndexError:
        return

    try:
        command_args = argv[2:]
    except IndexError:
        command_args = []

    migration = Migration()

    commands_map = {
        'prepare_migration_folders': migration.prepare_migration_folders,
        'make_migrations': migration.make_migrations,
        'migrate': migration.migrate
    }

    try:
        commands_map[command](*command_args)
    except KeyError:
        print(CMDStyle.red + f'Unknown command : {command}' + CMDStyle.reset)
    except TypeError as ex:
        print(CMDStyle.red + f'{ex}' + CMDStyle.reset)
    exit()
