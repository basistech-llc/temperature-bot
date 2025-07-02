from os.path import abspath,join,dirname

# Path to the schema file in the parent directory
MYDIR = dirname(abspath(__file__))
ROOT_DIR = dirname(MYDIR)
ETC_DIR = join(dirname(MYDIR),"etc")
SCHEMA_FILE_PATH = join(dirname(dirname(__file__)), 'etc', 'schema.sql')
DEV_DB = join(ROOT_DIR,'temperature-bot.db')
SECRETS_FILE = join(ROOT_DIR, 'secrets.json')
