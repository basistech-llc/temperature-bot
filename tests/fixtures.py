#!/usr/bin/env python3
"""
Legacy fixtures - now imports from conftest.py for backward compatibility.
"""
# Import all fixtures from conftest.py for backward compatibility
from conftest import (
    client,
    test_db_connection,
    test_db_name,
    setup_test_database,
    insert_temporal_test_data,
    skip_on_github,
    reduce_websockets_logging
)
