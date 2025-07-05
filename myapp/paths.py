from os.path import abspath,join,dirname

# Path to the schema file in the parent directory
APP_DIR = dirname(abspath(__file__))
ROOT_DIR = dirname(APP_DIR)
ETC_DIR = join(dirname(APP_DIR),"etc")
SCHEMA_FILE_PATH = join(dirname(dirname(__file__)), 'etc', 'schema.sql')
DEV_DB = join(ROOT_DIR,'temperature-bot.db')
SECRETS_PATH = join(ROOT_DIR, 'secrets.json')
