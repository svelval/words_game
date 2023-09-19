import numpy as np
from aiomysql import create_pool
from pymysql import IntegrityError


class MultipleObjectsExist(Exception):
    pass


class ObjectDoesNotExist(Exception):
    pass


class Database(object):
    _defaults = {}

    def __new__(cls, *args, **kwargs):
        if not hasattr(cls, 'instance'):
            cls.instance = super(Database, cls).__new__(cls)
        return cls.instance

    def __init__(self, db: str, defaults: dict = None):
        self._connection_pool = None
        self.__db = db
        if defaults is not None:
            self._defaults = defaults

    async def create_connection_pool(self):
        self._connection_pool = await create_pool(port=3306, user='root', password='velka2015', db=self.__db)

    def release_connection(self, conn):
        self._connection_pool.release(conn)

    async def close_all_connections(self):
        if self._connection_pool is not None:
            self._connection_pool.close()
            await self._connection_pool.wait_closed()

    async def filter(self, table: str, columns: list = None, condition: str = None,
                     connection=None, close_connection=True, **kwargs):
        if connection is None:
            conn = await self._connection_pool.acquire()
        else:
            conn = connection
        if columns is None:
            columns_to_select = '*'
            async with conn.cursor() as cur:
                await cur.execute(
                    f"SELECT COUNT(*) as `count` FROM information_schema.columns WHERE table_name='{table}'")
                columns_count = list(await cur.fetchall())[0][0]
        else:
            columns_to_select = ','.join('`' + str(item) + '`' for item in columns)
            columns_count = len(columns)
        join_tables = kwargs.get('join_tables')
        join_conditions = kwargs.get('join_conditions')
        join_command_part = ''
        if join_tables is not None:
            if join_conditions is None:
                raise AttributeError('"join_tables" cannot be passed without "join_conditions"')
            else:
                if len(join_tables) != len(join_conditions):
                    raise AttributeError('Lengths of "join_tables" and "join_conditions" must be the same')
                else:
                    for tab, cond in zip(join_tables, join_conditions):
                        join_command_part += f'JOIN {tab} ON {cond}\n'

        db_command = f"SELECT {columns_to_select} FROM `{table}`" + f' {join_command_part}'
        if condition is not None:
            db_command += f" WHERE {condition}"
        async with conn.cursor() as cur:
            await cur.execute(db_command)
            result = list(await cur.fetchall())

        if columns_count == 1:
            result = np.asarray(result).reshape(-1).tolist()
        if close_connection:
            self.release_connection(conn)
            return result
        else:
            return result, conn

    async def get(self, table: str, columns: list = None, condition: str = None, **kwargs):
        result, conn = await self.filter(table=table, columns=columns, condition=condition, close_connection=False, **kwargs)
        self.release_connection(conn)
        if len(result) == 0:
            raise ObjectDoesNotExist('No objects found')
        elif len(result) == 1:
            return result[0]
        else:
            raise MultipleObjectsExist('More than 1 objects found')


class CommonDatabase(Database):
    def __init__(self, *args, **kwargs):
        self.__db = 'words_game'
        super(CommonDatabase, self).__init__(db=self.__db, *args, **kwargs)

    async def __check_existence(self, table: str, columns: list, values: list,
                                columns_to_check: list = None, close_connection: bool = True):
        if columns_to_check is None:
            columns_check = columns
            values_check = values
        else:
            sorter = np.argsort(columns)
            indices = sorter[np.searchsorted(columns, columns_to_check, sorter=sorter)]
            columns_check = np.asarray(columns)[indices].tolist()
            values_check = np.asarray(values)[indices].tolist()
        exist_condition = ' AND '.join(
            col + "=" + "'" + str(val) + "'" for col, val in zip(columns_check, values_check))
        return await self.filter(table=table, columns=columns,
                                 condition=exist_condition,
                                 close_connection=close_connection)

    async def get_or_create(self, table: str, columns: list, values: list, **kwargs):
        found_objs, conn = await self.filter(table=table, columns=columns,
                                             condition=' AND '.join(
                                                 col + "=" + str(val) for col, val in zip(columns, values)),
                                             close_connection=False, **kwargs)
        if len(found_objs) == 0:
            table_defaults = self._defaults.get(table)
            if table_defaults is not None:
                columns += table_defaults.keys()
                values += table_defaults.values()

            async with conn.cursor() as cur:
                try:
                    await cur.execute(f"INSERT INTO `{table}` (" + ','.join(columns) +
                                      f") VALUES (" + ','.join("'" + str(item) + "'" for item in values) + ")")
                    await conn.commit()
                    self.release_connection(conn)
                    # return await self.get_columns(table=table, columns=columns)
                except Exception as e:
                    self.release_connection(conn)
                    raise Exception(str(e))
        elif len(found_objs) == 1:
            self.release_connection(conn)
            return found_objs
        else:
            self.release_connection(conn)
            raise MultipleObjectsExist('More than 1 object found')

    async def create_if_does_not_exist(self, table: str, columns: list, values: list, columns_to_check: list = None):
        found_objs, conn = await self.__check_existence(table=table, columns=columns, values=values,
                                                        columns_to_check=columns_to_check, close_connection=False)
        if len(found_objs) == 0:
            table_defaults = self._defaults.get(table)
            if table_defaults is not None:
                columns += table_defaults.keys()
                values += table_defaults.values()

            async with conn.cursor() as cur:
                try:
                    await cur.execute(f"INSERT INTO `{table}` (" + ','.join(columns) +
                                      f") VALUES (" + ','.join("'" + str(item) + "'" for item in values) + ")")
                    await conn.commit()
                    self.release_connection(conn)
                except IntegrityError:
                    self.release_connection(conn)
        else:
            self.release_connection(conn)

    async def create(self, table: str, columns: list, values: list, connection=None):
        if connection is None:
            conn = await self._connection_pool.acquire()
        else:
            conn = connection
        table_defaults = self._defaults.get(table)
        if table_defaults is not None:
            columns += table_defaults.keys()
            values += table_defaults.values()
        async with conn.cursor() as cur:
            await cur.execute(f"INSERT INTO `{table}` (" + ','.join(columns) +
                              f") VALUES (" + ','.join("'" + str(item) + "'" for item in values) + ")")
            await conn.commit()
        self.release_connection(conn)

    async def update(self, table: str, columns: list, values: list, condition: str, connection=None):
        if connection is None:
            conn = await self._connection_pool.acquire()
        else:
            conn = connection
        async with conn.cursor() as cur:
            found_objs, _ = await self.filter(table=table, columns=columns, condition=condition,
                                              connection=conn, close_connection=False)
            if len(found_objs) == 0:
                raise ObjectDoesNotExist('Object to update does not exist')
            else:
                update_list = ','.join(col + '=' + "'" + str(val) + "'" for col, val in zip(columns, values))
                await cur.execute(f'UPDATE `{table}` SET {update_list} WHERE {condition}')
                await conn.commit()
        self.release_connection(conn)

    async def update_or_create(self, table: str, columns: list, values: list, condition: str):
        found_objs, conn = await self.filter(table=table, columns=columns, condition=condition, close_connection=False)
        if len(found_objs) == 0:
            await self.create(table=table, columns=columns, values=values, connection=conn)
        else:
            await self.update(table=table, columns=columns, values=values, condition=condition, connection=conn)


class LanguagesDatabase(Database):
    def __init__(self, *args, **kwargs):
        self.__db = 'mafiabot_langs'
        super(LanguagesDatabase, self).__init__(db=self.__db, *args, **kwargs)

    async def get_text_content(self, dict_of_codenames: dict, lang_code: str, include_content_ids: bool = False):
        result = dict()

        async with self._connection_pool.acquire() as conn:
            async with conn.cursor() as cur:
                for table_type in dict_of_codenames.keys():
                    list_of_codenames = ','.join('"' + name + '"' for name in dict_of_codenames[table_type])
                    translations_query = 'SELECT translation'
                    originals_query = 'SELECT original_text'
                    if include_content_ids:
                        translations_query += ', text_content_id'
                        originals_query += ', id'
                    translations_query += f' FROM translations WHERE text_content_id in (SELECT id FROM text_content WHERE id in (SELECT text_content_id FROM mafiabot.`{table_type}` WHERE codename in ({list_of_codenames}))) AND lang_id=(SELECT id FROM languages WHERE lang_code="{lang_code}") ORDER BY text_content_id'
                    await cur.execute(translations_query)
                    translations_content = np.asarray(list(await cur.fetchall()))
                    if translations_content.ndim == 1:
                        translations = translations_content.tolist()
                    else:
                        translations = translations_content[:, 0].tolist()

                    originals_query += f' FROM text_content WHERE id in (SELECT text_content_id FROM mafiabot.`{table_type}` WHERE codename in ({list_of_codenames})) AND original_lang_id=(SELECT id FROM languages WHERE lang_code="{lang_code}") ORDER BY id'
                    await cur.execute(originals_query)
                    originals_content = np.asarray(list(await cur.fetchall()))
                    if originals_content.ndim == 1:
                        originals = originals_content.tolist()
                    else:
                        originals = originals_content[:, 0].tolist()

                    result_text_content = translations + originals
                    if include_content_ids:
                        translations_lang_ids = translations_content[:, 1].astype('int')
                        originals_lang_ids = originals_content[:, 1].astype('int')
                        result_lang_ids = np.concatenate((translations_lang_ids, originals_lang_ids))
                        result[table_type] = dict()
                        result[table_type]['content'] = result_text_content
                        result[table_type]['content_ids'] = result_lang_ids
                    else:
                        result[table_type] = result_text_content

        if len(result) == 1:
            result_list = list(result.values())[0]
            if len(result_list) == 1:
                return result_list[0]
            else:
                return result_list
        else:
            return result

    async def get_all_lang_codes(self):
        async with self._connection_pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(f'SELECT lang_code FROM `languages` ORDER BY id')
                return np.asarray(list(await cur.fetchall())).reshape(-1).tolist()

    async def get_all_lang_ids(self):
        async with self._connection_pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(f'SELECT id FROM `languages` ORDER BY id')
                return np.asarray(list(await cur.fetchall())).reshape(-1).tolist()
