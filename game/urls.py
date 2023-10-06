from quart import Blueprint

from game.error_handlers import not_found, obj_not_found
from game.exceptions import ObjectNotFound
from game.preprocessors import before_request, context_processor, after_request
from game.views import index, login, login_post, user

game_blueprint = Blueprint('game', __name__, template_folder='templates', static_folder='static')
game_blueprint.before_request(before_request)
game_blueprint.context_processor(context_processor)
game_blueprint.after_request(after_request)

game_blueprint.register_error_handler(404, not_found)
game_blueprint.register_error_handler(ObjectNotFound, obj_not_found)

game_blueprint.add_url_rule('/', view_func=index)
game_blueprint.add_url_rule('/login', view_func=login)
game_blueprint.add_url_rule('/login', view_func=login_post, methods=['POST'])
game_blueprint.add_url_rule('/user', view_func=user)
