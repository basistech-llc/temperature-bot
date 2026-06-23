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

# Air-quality-like devices older than this are hidden from the main dashboard.
DASHBOARD_AIR_QUALITY_DEVICE_EXPIRATION_SECONDS = 30 * 24 * 60 * 60

# FCU set ranges must be at least this wide, in degrees Celsius.
MIN_SET_RANGE_C = 3.0
DEFAULT_SET_RANGE_CENTER_C = 21.0
