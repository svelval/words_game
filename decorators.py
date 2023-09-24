from inspect import iscoroutinefunction

from pymysql import OperationalError


def database_errors_handler(fun):
    async def wrapper(*args, **kwargs):
        try:
            if iscoroutinefunction(fun):
                await fun(*args, **kwargs)
            else:
                fun(*args, **kwargs)
        except (AttributeError, NameError):
            print('Connection pool does not exist')
        except OperationalError as ex:
            print(f'Connection pool cannot be created: {ex}')
    return wrapper
