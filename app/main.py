"""
Refactored main.py - Flask application with modular structure
"""

import datetime
import logging
import os
from functools import lru_cache
from os.path import abspath
from pathlib import Path
from urllib.parse import quote
from flask import Flask, send_from_directory, jsonify
from werkzeug.exceptions import HTTPException
from werkzeug.middleware.proxy_fix import ProxyFix

from . import db
from . import room_config
from . import routes_api
from . import routes_web
from .performance_routes import performance_routes
from .ae200_routes import ae200_routes
from .instance_policy import ControlMode, InstancePolicy, load_instance_policy
from .models import ApplicationMetadata, json_ready
from .version import __version__, git_branch, git_sha

DEV = "/home/simsong" in abspath(__file__)
DEFAULT_LOG_LEVEL = "DEBUG"
LOGGING_CONFIG = "%(asctime)s  %(filename)s:%(lineno)d %(levelname)s: %(message)s"
LOG_LEVEL = os.getenv("LOG_LEVEL", DEFAULT_LOG_LEVEL).upper()
LOG_LEVEL = "DEBUG"
APP_DIR = Path(__file__).resolve().parent
REPO_DIR = APP_DIR.parent
GITHUB_REPO_URL = "https://github.com/basistech-llc/temperature-bot"


def _format_mtime(path: Path) -> str:
    """Return a local timestamp string for a filesystem path mtime."""
    return datetime.datetime.fromtimestamp(path.stat().st_mtime).strftime(
        "%Y-%m-%d %H:%M:%S"
    )


def _mtime_year(path: Path) -> int:
    """Return the local year for a filesystem path mtime."""
    return datetime.datetime.fromtimestamp(path.stat().st_mtime).year


def _git_commit() -> str:
    """Return the current git commit for this checkout, if available."""
    return git_sha()


def _git_branch() -> str:
    """Return the current git branch for this checkout, if available."""
    return git_branch()


def _github_branch_url(branch: str) -> str:
    """Return the GitHub URL for a branch in this repository."""
    return f"{GITHUB_REPO_URL}/tree/{quote(branch, safe='/')}"


@lru_cache(maxsize=1)
def application_metadata() -> ApplicationMetadata:
    """Return metadata displayed in the site footer."""
    branch = _git_branch()
    return ApplicationMetadata(
        app_version=__version__,
        deployment_date=_format_mtime(APP_DIR),
        deployment_year=_mtime_year(APP_DIR),
        git_branch_url=_github_branch_url(branch),
        git_commit=_git_commit(),
    )


def fix_boto_log_level():
    """Do not run boto loggers at debug level"""
    for name in logging.root.manager.loggerDict:  # pylint: disable=no-member
        if name.startswith("boto"):
            logging.getLogger(name).setLevel(logging.INFO)


def create_app(instance_policy: InstancePolicy | None = None):
    """Create and configure the Flask application"""
    policy = instance_policy or load_instance_policy()
    # https://flask.palletsprojects.com/en/stable/config/
    app = Flask(__name__)
    setattr(app, "wsgi_app", ProxyFix(app.wsgi_app, x_for=1, x_proto=1))
    app.config["TEMPLATES_AUTO_RELOAD"] = True
    # Make flask_pydantic raise instead of writing its own {"validation_error": ...}
    # body, so app/api_errors.py is the single place that formats API failures.
    app.config["FLASK_PYDANTIC_VALIDATION_ERROR_RAISE"] = True
    app.config["INSTANCE_POLICY"] = policy

    # Configure logging
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(format=LOGGING_CONFIG, level=log_level, force=True)
    app.logger.info("new Flask(__name__=%s) log_level=%s", __name__, log_level)
    fix_boto_log_level()
    db.validate_database_schema_on_startup()

    @app.context_processor
    def deployment_context():
        return {
            "simulator_mode": policy.control_mode is ControlMode.SIMULATOR,
            "instance_name": policy.instance,
            "room_dashboards": sorted(
                room_config.ROOM_CONFIGS.values(), key=lambda config: config.label
            ),
            **json_ready(application_metadata()),
        }

    # Register blueprints
    app.register_blueprint(routes_api.api_v1, url_prefix="/api/v1")
    app.register_blueprint(performance_routes)
    app.register_blueprint(ae200_routes)

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
