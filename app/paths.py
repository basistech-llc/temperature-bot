"""
Paths
"""

from pathlib import Path
from os.path import abspath,join,dirname
import os

# Path to the schema file in the parent directory
TIMEOUT_SECONDS = 2
APP_DIR = dirname(abspath(__file__))
ROOT_DIR = dirname(APP_DIR)
ETC_DIR = join(dirname(APP_DIR),"etc")
SCHEMA_FILE_PATH = join(dirname(dirname(__file__)), 'etc', 'schema.sql')
CONFIG_YAML_PATH = join(ROOT_DIR, 'config.yaml')
DEV_DB_PATH = join(ROOT_DIR,'temperature-bot.db')
DB_PATH = Path(os.getenv("DB_PATH", DEV_DB_PATH))
