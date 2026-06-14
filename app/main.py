"""
Refactored main.py - Flask application with modular structure
"""

import os
import logging
from os.path import abspath
from flask import Flask, send_from_directory, jsonify
from werkzeug.exceptions import HTTPException
from werkzeug.middleware.proxy_fix import ProxyFix

from . import routes_api
from . import routes_web

DEV = "/home/simsong" in abspath(__file__)
DEFAULT_LOG_LEVEL = "DEBUG"
LOGGING_CONFIG = "%(asctime)s  %(filename)s:%(lineno)d %(levelname)s: %(message)s"
LOG_LEVEL = os.getenv("LOG_LEVEL", DEFAULT_LOG_LEVEL).upper()
LOG_LEVEL = "DEBUG"

def fix_boto_log_level():
    """Do not run boto loggers at debug level"""
    for name in logging.root.manager.loggerDict:  # pylint: disable=no-member
        if name.startswith("boto"):
            logging.getLogger(name).setLevel(logging.INFO)

def create_app():
    """Create and configure the Flask application"""




    # https://flask.palletsprojects.com/en/stable/config/
    app = Flask(__name__)
    setattr(app, "wsgi_app", ProxyFix(app.wsgi_app, x_for=1, x_proto=1))
    app.config["TEMPLATES_AUTO_RELOAD"] = True

    # Configure logging
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(format=LOGGING_CONFIG, level=log_level, force=True)
    app.logger.info("new Flask(__name__=%s) log_level=%s", __name__, log_level)
    fix_boto_log_level()

    # Register blueprints
    app.register_blueprint(routes_api.api_v1, url_prefix="/api/v1")

    # Register web routes
    routes_web.create_web_routes(app)

    # Serve static files
    @app.route("/static/<path:filename>")
    def static_files(filename):
        return send_from_directory("static", filename)

    # Error handler
    @app.errorhandler(HTTPException)
    def handle_exception(e):
        return jsonify({"error": e.description}), e.code

    return app

# Create the app instance
app = create_app()
