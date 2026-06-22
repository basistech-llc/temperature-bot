"""
Tests for the master rules kill switch behaviour.
"""

import time
from unittest.mock import patch

from app import db
from app import rules_engine


def test_run_rules_respects_master_switch(test_database_conn_with_test_data):
    """run_rules should completely skip rule execution when the master switch is OFF."""
    conn = test_database_conn_with_test_data[0]

    # Ensure master is OFF
    db.set_rules_master_enabled(conn, False)
    assert db.get_rules_master_enabled(conn) is False

    # When master is OFF, run_rules should return early and never exec any rules.
    with patch("app.rules_engine.get_rules") as mock_get_rules:
        rules_engine.run_all_rules(conn)
        mock_get_rules.assert_not_called()

    # Turn master back ON
    db.set_rules_master_enabled(conn, True)
    assert db.get_rules_master_enabled(conn) is True

    # When master is ON, run_rules should attempt to load rules (and thus call get_rules).
    with patch("app.rules_engine.get_rules") as mock_get_rules:
        # Return a no-op rules script; we only care that it was requested.
        mock_get_rules.return_value = "pass\n"
        rules_engine.run_all_rules(conn, when=time.time())
        mock_get_rules.assert_called_once()
