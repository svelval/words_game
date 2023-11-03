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
        self.created_indexes_info = {}
        self.created_triggers_info = {}
        self.migrations_creations = {}
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
        migration_data = re.sub('["\'`]', '', migration_data)
        migration_data = re.sub('[()]', lambda match: ' (' if match.group() == '(' else ') ', migration_data)
        migration_data = re.sub('\)\s+;', ');', migration_data)
        return re.sub('\s*\)', ')', migration_data)

    def __create_migrations_db_table(self):
        try:
            migrations_db_info = settings.MIGRATIONS_TABLE_INFO
        except (AttributeError, KeyError):
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

    def __file_is_potential_migration(self, filename, allowed_extensions, file_directory_path=...):
        if isinstance(allowed_extensions, str):
            allowed_extensions = [allowed_extensions]
        return (self.file_extension(filename) in allowed_extensions) and (re.search('^[a-zA-Z_]', filename) is not None) \
               and ((file_directory_path is Ellipsis) or (not os.path.isdir(os.path.join(file_directory_path, filename))))

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
        def inner(self, migration_data, migration_db, dependencies, migration_blueprint=...,
                  migration_creations_dict_key=...):
            migration_warnings = []
            args = (self, migration_data, migration_db, dependencies, migration_warnings)
            kwargs = {}
            if migration_blueprint is not Ellipsis:
                kwargs['migration_blueprint'] = migration_blueprint
            if migration_creations_dict_key is not Ellipsis:
                kwargs['migration_creations_dict_key'] = migration_creations_dict_key
            making_fun(*args, **kwargs)
            if migration_warnings:
                print(CMDStyle.orange + f'\t\t\tWARNINGS:' + '\n\t\t\t\t- '.join(
                    migration_warnings) + CMDStyle.reset)
            migration_warnings.clear()
        return inner

    def __add_creation(self, creation_obj_name, blueprint_name, migration, migration_db_folder,
                       table_name=..., columns=..., creation_dict=...):
        creation_info = {
            'blueprint': blueprint_name,
            'db': self.blueprints_db_settings[blueprint_name][migration_db_folder]['name'],
            'db_folder': migration_db_folder,
            'migration': migration,
        }
        if table_name is not Ellipsis:
            creation_info['table'] = table_name
        if columns is not Ellipsis:
            creation_info['columns'] = columns
        if creation_obj_name not in creation_dict:
            creation_dict[creation_obj_name] = []
        creation_dict[creation_obj_name].append(creation_info)

    def __add_table_creation(self, table_name, blueprint_name, migration, migration_db_folder, columns):
        self.__add_creation(creation_obj_name=table_name, blueprint_name=blueprint_name, migration=migration,
                            migration_db_folder=migration_db_folder, columns=columns,
                            creation_dict=self.created_tables_info)

    def __add_index_or_trigger_creation(self, creation_type, index_of_trigger_name, blueprint_name, table_name,
                                        migration, migration_db_folder, columns=...):
        migration_path = f'{blueprint_name}/{migration_db_folder}/{migration}'
        if migration_path not in self.migrations_creations:
            self.migrations_creations[migration_path] = {
                'index_names': [],
                'index_tables': [],
                'index_columns': [],
                'trigger_names': [],
                'trigger_tables': [],
            }
        if creation_type == 'index':
            creation_dict = self.created_indexes_info
            if columns is not Ellipsis:
                self.migrations_creations[migration_path]['index_names'].append(index_of_trigger_name)
                self.migrations_creations[migration_path]['index_tables'].append(table_name)
                self.migrations_creations[migration_path]['index_columns'].append(columns)
        else:
            creation_dict = self.created_triggers_info
            self.migrations_creations[migration_path][f'trigger_names'].append(index_of_trigger_name)
            self.migrations_creations[migration_path][f'trigger_tables'].append(table_name)
        self.__add_creation(creation_obj_name=index_of_trigger_name, blueprint_name=blueprint_name, table_name=table_name,
                            migration=migration, migration_db_folder=migration_db_folder, columns=columns,
                            creation_dict=creation_dict)

    def __search_suitable_creation(self, obj_of_creation, obj_db, warning, migration_dependencies, migration_warnings,
                                   table_name=..., table_blueprint=..., table_cols=..., find_creation_in=...):
        if not isinstance(find_creation_in, dict):
            find_creation_in = self.created_tables_info
        if not isinstance(table_cols, (str, list)):
            table_cols = []
        if isinstance(table_cols, str):
            table_cols = [table_cols]
        migration_warnings.append(warning)
        try:
            related_creations = list(
                map(lambda creation_info: creation_info
                if creation_info['db'] == obj_db and
                   ((table_blueprint is Ellipsis) or (creation_info['blueprint'] == table_blueprint)) and
                   ((table_name is Ellipsis) or (creation_info['table'] == table_name)) and
                   all(table_col in creation_info['columns'] for table_col in table_cols) else None,
                    find_creation_in[obj_of_creation])
            )
        except KeyError:
            return
        related_suitable_creations = [creation for creation in related_creations if creation is not None]
        if related_suitable_creations:
            suitable_creation_blueprint = related_suitable_creations[0]['blueprint']
            suitable_creation_db_folder = related_suitable_creations[0]['db_folder']
            suitable_creation_migration = os.path.splitext(related_suitable_creations[0]['migration'])[0]
            dependency = f'{suitable_creation_blueprint}/{suitable_creation_db_folder}/{suitable_creation_migration}'
            if dependency not in migration_dependencies:
                migration_dependencies.append(dependency)
            migration_warnings.remove(warning)

    def search_suitable_table_creation(self, table, table_db, warning,
                                       migration_dependencies, migration_warnings, table_cols=..., table_blueprint=...):
        self.__search_suitable_creation(table, table_db, warning, migration_dependencies, migration_warnings,
                                        table_blueprint=table_blueprint, table_cols=table_cols)

    def search_suitable_index_creation(self, index, index_db, index_table, warning, migration_dependencies,
                                       migration_warnings, table_blueprint):
        self.__search_suitable_creation(index, index_db, warning, migration_dependencies, migration_warnings,
                                        table_name=index_table, table_blueprint=table_blueprint,
                                        find_creation_in=self.created_indexes_info)

    def search_suitable_trigger_creation(self, trigger, trigger_db, blueprint, warning, migration_dependencies,
                                         migration_warnings):
        self.__search_suitable_creation(trigger, trigger_db, warning, migration_dependencies, migration_warnings,
                                        table_blueprint=blueprint, find_creation_in=self.created_triggers_info)

    @__make_dependencies
    def make_foreign_keys_dependencies(self, migration_data, migration_db, dependencies, migration_warnings):
        print(f'\t\t\tCurrent operation: making dependencies for foreign keys...')
        foreign_keys = re.findall('foreign\s+key\s+\S+\s*\(.*\)\s+references\s+\S+\s*\(\S+\)', migration_data)
        foreign_keys_split = [foreign_key.split() for foreign_key in foreign_keys]
        for foreign_key_info in foreign_keys_split:
            if '(' not in foreign_key_info[2]:
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

            self.search_suitable_table_creation(related_table, related_table_db,
                                                f'Related table "{related_table_db}.{related_table}" of foreign key '
                                                f'"{foreign_key_name}" is not created in any migration',
                                                dependencies, migration_warnings, table_cols=related_table_column)

    @__make_dependencies
    def make_alter_table_dependencies(self, migration_data, migration_db, dependencies,
                                      migration_warnings, migration_blueprint):
        print(f'\t\t\tCurrent operation: making dependencies for alter tables...')
        alters_tables = [stmt.replace(';', ' ') for stmt in re.findall('alter\s+table\s+.*;?', migration_data)]
        for alter_table_str in alters_tables:
            altering_table = alter_table_str.split()[2]
            if altering_table not in self.created_tables_info:
                migration_warnings.append(
                    f'Altering table "{altering_table}" is not created in any migration')
                continue
            alter_table_body = re.sub('alter\s+table\s+\S+\s+', '', alter_table_str)
            columns_to_edit = [re.split('\s+column\s+', stmt)[-1].split()[0] for stmt in
                               re.split(',\s*', alter_table_body)
                               if 'column' in stmt]
            indexes_to_edit = [re.sub('[,;]', ' ', stmt.group()).split('index')[-1].split()[0] for stmt in
                               re.finditer('\s+index\s+\S+\s*[,;]?', alter_table_body)]
            self.search_suitable_table_creation(altering_table, migration_db,
                                                f'Altering table "{altering_table}" with '
                                                f'columns ({", ".join(columns_to_edit)}) is not created in any migration',
                                                dependencies, migration_warnings, table_cols=columns_to_edit,
                                                table_blueprint=migration_blueprint)
            for index in indexes_to_edit:
                self.search_suitable_index_creation(index, migration_db, altering_table,
                                                    f'Altering table "{altering_table}" with '
                                                    f'indexes ({", ".join(indexes_to_edit)})'
                                                    f' is not created in any migration',
                                                    dependencies, migration_warnings, migration_blueprint)

    @__make_dependencies
    def make_create_index_dependencies(self, migration_data, migration_db, dependencies, migration_warnings,
                                       migration_creations_dict_key, migration_blueprint,):
        print(f'\t\t\tCurrent operation: making dependencies for create indexes...')
        if migration_creations_dict_key not in self.migrations_creations:
            return
        migration_indexes_creations = list(self.migrations_creations[migration_creations_dict_key].values())[:3]
        for index_name, index_table, index_columns in zip(*migration_indexes_creations):
            if index_table not in self.created_tables_info:
                migration_warnings.append(
                    f'Indexing table "{index_table}" is not created in any migration')
                continue
            self.search_suitable_table_creation(index_table, migration_db,
                                                f'Table "{index_table}" with columns ({", ".join(index_columns)}) '
                                                f'to indexing is not created in any migration',
                                                dependencies, migration_warnings, table_cols=index_columns,
                                                table_blueprint=migration_blueprint)

    @__make_dependencies
    def make_create_trigger_dependencies(self, migration_data, migration_db, dependencies, migration_warnings,
                                         migration_creations_dict_key, migration_blueprint,):
        print(f'\t\t\tCurrent operation: making dependencies for create triggers...')
        if migration_creations_dict_key not in self.migrations_creations:
            return
        migration_triggers_creations = list(self.migrations_creations[migration_creations_dict_key].values())[3:]
        for trigger_name, trigger_table in zip(*migration_triggers_creations):
            if trigger_table not in self.created_tables_info:
                migration_warnings.append(
                    f'Table "{trigger_table}" inside "{trigger_name}" trigger is not created in any migration')
                continue
            self.search_suitable_table_creation(trigger_table, migration_db,
                                                f'Trigger "{trigger_name}" on table "{trigger_table}" is not created '
                                                f'in any migration',
                                                dependencies, migration_warnings, table_blueprint=migration_blueprint)

    @__make_dependencies
    def make_drop_trigger_dependencies(self, migration_data, migration_db, dependencies, migration_warnings,
                                       migration_blueprint):
        print(f'\t\t\tCurrent operation: making dependencies for dropped triggers...')
        trigger_drops = [stmt.replace(';', ' ') for stmt in re.findall('drop\s+trigger\s+\S+\s*;?', migration_data)]
        for drop_trigger_str in trigger_drops:
            dropped_trigger_name = drop_trigger_str.split()[2]
            if dropped_trigger_name not in self.created_triggers_info:
                migration_warnings.append(
                    f'Trigger "{dropped_trigger_name}" is not created in any migration')
                continue
            self.search_suitable_trigger_creation(dropped_trigger_name, migration_db, migration_blueprint,
                                                  f'Trigger "{dropped_trigger_name}" is not created in any migration',
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
                                        if self.__file_is_potential_migration(filename, ['sql', 'py'],
                                                                              file_directory_path=migrations_db_folder_path)]
                    for migration in migrations_files:
                        with open(os.path.join(migrations_db_folder_path, migration), 'r') as data:
                            migration_data = self.__prepare_migration_data(data.read())
                        migration_tables_creations = re.findall('create\s+table\s+\S+\s*\(.*\);?', migration_data)
                        for table_creation_info in migration_tables_creations:
                            table_creation_info_split = table_creation_info.split()
                            table_name = re.sub('["\'`]', '', table_creation_info_split[2])
                            table_info_without_keys = re.sub('[(,]?\s*((foreign)|(primary)|(unique)\s+key)\s+\S*\s*\(.*\)', '',
                                                             table_creation_info)
                            table_indexes_re = '\S*\s*index\s+\S*\s*\(.+\),?'
                            table_index_creations = re.findall(table_indexes_re, table_info_without_keys)
                            table_info_without_indexes = re.sub(table_indexes_re, '', table_info_without_keys)
                            only_column_defs = re.sub('create\s+table\s+\S+\s+\(', '', table_info_without_indexes)
                            table_columns_info = re.split(',\s*', only_column_defs)
                            self.__add_table_creation(table_name, blueprint_name, migration, migration_db_folder,
                                                      columns=[columns_info_entities.split()[0]
                                                               for columns_info_entities in table_columns_info])
                            for index_creation in table_index_creations:
                                index_creation_split = index_creation.split('index')[-1].split()
                                index_name = re.sub('[()]', '', index_creation_split[0])
                                self.__add_index_or_trigger_creation('index', index_name, blueprint_name, table_name,
                                                                     migration, migration_db_folder)

                        migration_indexes_creations = re.findall('create\s+index\s+\S+\s+on\s+\S+\s+\(.+\)',
                                                                 migration_data)
                        for index_creation in migration_indexes_creations:
                            index_creation_split = index_creation.split()
                            index_name = index_creation_split[2]
                            index_table = index_creation_split[4]
                            index_columns = re.split(',\s*', re.sub('[()]', '', index_creation_split[5]))
                            self.__add_index_or_trigger_creation('index', index_name, blueprint_name, index_table,
                                                                 migration, migration_db_folder, columns=index_columns)

                        migration_triggers_creations = [match.group() for match in
                                                        re.finditer('create\s+trigger\s+(if\s+not\s+exists)?\s+\S+\s'
                                                                    '(before|after)\s+(create|update|delete)\s+on\s+\S+\s+',
                                                                    migration_data)]
                        for trigger_creation in migration_triggers_creations:
                            trigger_creation_split = trigger_creation.split()
                            if re.search('if\s+not\s+exists', trigger_creation_split[2]) is not None:
                                trigger_name = trigger_creation_split[3]
                                trigger_table = trigger_creation_split[6]
                            else:
                                trigger_name = trigger_creation_split[2]
                                trigger_table = trigger_creation_split[5]
                            self.__add_index_or_trigger_creation('trigger', trigger_name, blueprint_name, trigger_table,
                                                                 migration, migration_db_folder)
            except FileNotFoundError:
                blueprints_names.remove(blueprint_name)
                continue

        for blueprint_name, blueprint_migrations_folders in zip(blueprints_names, migrations_folders):
            print('Making migrations for blueprint ' + CMDStyle.yellow + blueprint_name + CMDStyle.reset + '...')
            for migrations_folder in blueprint_migrations_folders:
                migrations_db_folder_path = os.path.join(blueprint_name, 'migrations', migrations_folder)
                migrations_files = [filename for filename in os.listdir(migrations_db_folder_path)
                                    if self.__file_is_potential_migration(filename, 'sql',
                                                                          file_directory_path=migrations_db_folder_path)]
                migration_db = self.blueprints_db_settings[blueprint_name][migrations_folder]['name']
                if migrations_files:
                    print('\tIn folder ' + CMDStyle.yellow + migrations_folder + CMDStyle.reset + '...')
                for i, migration in enumerate(migrations_files):
                    print(f'\t\t{i + 1}. From file ' + CMDStyle.yellow + migration + CMDStyle.reset + '...')
                    migration_path = os.path.join(migrations_db_folder_path, migration)
                    migration_dependencies = []
                    with open(migration_path, 'r') as data:
                        migration_data_original = data.read()
                    migration_data = self.__prepare_migration_data(migration_data_original)

                    migration_creations_dict_key = f'{blueprint_name}/{migrations_folder}/{migration}'
                    self.make_foreign_keys_dependencies(migration_data, migration_db, migration_dependencies)
                    self.make_alter_table_dependencies(migration_data, migration_db, migration_dependencies,
                                                       migration_blueprint=blueprint_name)
                    self.make_create_index_dependencies(migration_data, migration_db, migration_dependencies,
                                                        migration_blueprint=blueprint_name,
                                                        migration_creations_dict_key=migration_creations_dict_key)
                    self.make_create_trigger_dependencies(migration_data, migration_db, migration_dependencies,
                                                          migration_blueprint=blueprint_name,
                                                          migration_creations_dict_key=migration_creations_dict_key)
                    self.make_drop_trigger_dependencies(migration_data, migration_db, migration_dependencies,
                                                        migration_blueprint=blueprint_name)

                    # TODO: то же самое, только с ALTER_TABLE
                    if migration_dependencies:
                        migration_dependencies_in_file = re.sub('[\[\]]', '',
                                                                str(migration_dependencies).replace(" ", "\n\t"))
                        migration_dependencies_in_file = f'[\n\t{migration_dependencies_in_file}\n]'
                    else:
                        migration_dependencies_in_file = '[]'
                    with open(migration_path[:-3] + 'py', 'w') as new_migration:
                        new_migration.write(
                            f'dependencies = {migration_dependencies_in_file}\n\noperations = \'\'\'{migration_data_original}\'\'\'')
                        print(
                            f'\t\t\tMigration file ' + CMDStyle.yellow + new_migration.name + CMDStyle.reset + ' CREATED')

    def migrate(self):
        try:
            self.__create_migrations_db_table()
        except (AttributeError, KeyError, TypeError, ProgrammingError) as error:
            if isinstance(error, (AttributeError, KeyError)):
                error_msg = 'Database to save migrations is not specified. Check if you set MIGRATIONS_TABLE_INFO ' \
                            'or correct \'default\' database inside DATABASES_INFO in ' + CMDStyle.yellow + 'settings.py'
            elif isinstance(error, ProgrammingError):
                error_msg = f'Wrong data of migrations database : ' + CMDStyle.bold + str(error)
            else:
                error_msg = f'Wrong MIGRATIONS_TABLE_INFO or \'default\' DB in DATABASES_INFO : ' + CMDStyle.bold + str(error)
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
                                    if self.__file_is_potential_migration(filename, 'py',
                                                                          file_directory_path=migrations_db_folder_path)]
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
