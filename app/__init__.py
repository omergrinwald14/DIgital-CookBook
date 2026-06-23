"""Application factory.

Using a factory (`create_app`) instead of a module-level Flask instance keeps
the app importable for tests and lets us configure it differently per
environment. Routes are registered via blueprints so each feature lives in its
own module.
"""

from flask import Flask

from config import Config
from app.routes.recipe import recipe_bp


def create_app(config_class=Config):
    """Build and configure a Flask application instance."""
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Register feature blueprints. As the cookbook grows (parsing, storage,
    # auth, ...) each new area gets its own blueprint registered here.
    app.register_blueprint(recipe_bp)

    return app
