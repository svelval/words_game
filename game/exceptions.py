from werkzeug.exceptions import HTTPException


class ObjectNotFound(HTTPException):
    code = 460
    description = 'Object not found'

    def __init__(self, obj, obj_name):
        self.obj = obj
        self.obj_name = obj_name
