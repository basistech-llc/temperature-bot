"""
Database utility functions
"""
import logging
from functools import wraps
from .. import db


logger = logging.getLogger(__name__)


def get_db_connection():
    """Get database connection for current request"""
    return db.get_db_connection()


def with_db_connection(f):
    """Decorator to handle database connections properly"""

    @wraps(f)
    def decorated_function(*args, **kwargs):
        conn = get_db_connection()
        try:
            return f(conn, *args, **kwargs)
        finally:
            conn.close()

    return decorated_function
