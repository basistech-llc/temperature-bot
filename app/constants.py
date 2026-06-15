"""
Application constants
"""
__version__ = "0.0.1"

# Environment variables
TEST_DB_NAME = 'TEST_DB_NAME'
DB_PATH = 'DB_PATH'
RULES_DISABLE_SECONDS = 60*60*3

# A temperature source older than this is ignored when computing an FCU's
# calculated room temperature.
TEMP_SOURCE_STALE_SECONDS = 10 * 60
