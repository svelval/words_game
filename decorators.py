from inspect import iscoroutinefunction

from pymysql import OperationalError

from database_exceptions import ConnectionPoolCannotBeCreated, ConnectionPoolDoesNotExist, InternalDatabaseError


def database_errors_handler(fun):
    async def wrapper(*args, **kwargs):
        try:
            if iscoroutinefunction(fun):
                await fun(*args, **kwargs)
            else:
                fun(*args, **kwargs)
        except (AttributeError, NameError):
            raise ConnectionPoolDoesNotExist('Connection pool does not exist')
        except OperationalError as ex:
            raise ConnectionPoolCannotBeCreated(f'Connection pool cannot be created: {ex}')
        except Exception as other_ex:
            raise InternalDatabaseError(f'Internal database error: {other_ex}')
    return wrapper
