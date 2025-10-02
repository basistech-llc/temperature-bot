"""
Paths and constants
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
CONFIG_YAML_PATH = Path(os.getenv('TEMPERATURE_BOT_CONFIG',join(ROOT_DIR, 'temperature-bot-config.yaml')))
TEST_DIR    = join(ROOT_DIR,'tests')
TEST_DATA_DIR = join(TEST_DIR,'data')
LOGGING_CONFIG='%(asctime)s  %(filename)s:%(lineno)d %(levelname)s: %(message)s'

def db_path():
    if 'TEST_DB_PATH' in os.environ:
        return Path(os.environ['TEST_DB_PATH'])
    if 'DB_PATH' in os.environ:
        return Path(os.environ['DB_PATH'])
    raise RuntimeError('Neither DB_PATH nor TEST_DB_NAME are set.')

def dev_db_path():
    Path(os.getenv('DEV_DB_PATH',join(ROOT_DIR,'temperature-bot.db')))
