from quart import Quart

from game.preprocessors import on_startup, on_shutdown
from game.urls import game_blueprint

app = Quart(__name__, static_folder=None)
app.register_blueprint(game_blueprint)

app.before_serving(on_startup)
app.after_serving(on_shutdown)
