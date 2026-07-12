"""
Refactored main.py - Flask application with modular structure
"""

import datetime
import logging
import os
import subprocess
import sys
from functools import lru_cache
from os.path import abspath
from pathlib import Path
from urllib.parse import quote
from flask import Flask, send_from_directory, jsonify
from werkzeug.exceptions import HTTPException
from werkzeug.middleware.proxy_fix import ProxyFix

from . import ae200
from . import db
from . import routes_api
from . import routes_web
from .constants import __version__
from .models import ApplicationMetadata, json_ready

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


def _git_commit(repo_dir: Path) -> str:
    """Return the current git commit for this checkout, if available."""
    env_commit = os.getenv("GIT_COMMIT") or os.getenv("COMMIT_SHA")
    if env_commit:
        return env_commit[:12]
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_dir), "rev-parse", "--short=12", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            timeout=1,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return "unknown"
    return result.stdout.strip() or "unknown"


def _git_branch(repo_dir: Path) -> str:
    """Return the current git branch for this checkout, if available."""
    env_branch = os.getenv("GIT_BRANCH") or os.getenv("BRANCH_NAME")
    if env_branch:
        return env_branch.removeprefix("origin/")
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_dir), "rev-parse", "--abbrev-ref", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            timeout=1,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return "unknown"
    return result.stdout.strip() or "unknown"


def _github_branch_url(branch: str) -> str:
    """Return the GitHub URL for a branch in this repository."""
    return f"{GITHUB_REPO_URL}/tree/{quote(branch, safe='/')}"


@lru_cache(maxsize=1)
def application_metadata() -> ApplicationMetadata:
    """Return metadata displayed in the site footer."""
    git_branch = _git_branch(REPO_DIR)
    return ApplicationMetadata(
        app_version=__version__,
        deployment_date=_format_mtime(APP_DIR),
        deployment_year=_mtime_year(APP_DIR),
        git_branch_url=_github_branch_url(git_branch),
        git_commit=_git_commit(REPO_DIR),
    )


def fix_boto_log_level():
    """Do not run boto loggers at debug level"""
    for name in logging.root.manager.loggerDict:  # pylint: disable=no-member
        if name.startswith("boto"):
            logging.getLogger(name).setLevel(logging.INFO)


def should_validate_database_schema_on_startup() -> bool:
    """Return whether this process should validate the runtime DB at startup."""
    return "PYTEST" not in os.environ and db.TEST_DB_NAME not in os.environ


def validate_database_schema_on_startup() -> None:
    """Stop Flask startup when the configured database is not current."""
    if not should_validate_database_schema_on_startup():
        return
    try:
        db.validate_configured_database_schema()
    except db.DatabaseSchemaMismatchError as e:
        print(str(e), file=sys.stderr)
        raise SystemExit(1) from None


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
    validate_database_schema_on_startup()

    @app.context_processor
    def simulator_context():
        return {
            "ae200_simulator": bool(ae200.AE200_SIMULATOR),
            **json_ready(application_metadata()),
        }

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
