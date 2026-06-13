"""
test aqi endpoint
"""

import logging
import time

from app import airquality
from app import db

logger = logging.getLogger(__name__)


def test_aqi_decode():
    assert airquality.aqi_decode(50) == {
        "value": 50,
        "name": "Good",
        "color_name": "Green",
        "color": "#00e400",
    }


def test_aqicn_simulator_env_requires_enabled_value(monkeypatch):
    """AQICN simulator mode should not treat every non-empty value as enabled."""
    for value in ("0", "false", "False", "no", "off", ""):
        monkeypatch.setenv(airquality.AQICN_SIMULATOR_ENV, value)
        assert not airquality.aqicn_simulator_enabled()

    for value in ("1", "true", "TRUE", "yes", "on"):
        monkeypatch.setenv(airquality.AQICN_SIMULATOR_ENV, value)
        assert airquality.aqicn_simulator_enabled()


def test_aqi_rest(flask_test_client, test_database_conn_with_test_data):  # noqa: F811
    conn = test_database_conn_with_test_data[0]
    now = int(time.time()) + 10
    qdata = {
        "logtime": now,
        "aqi": 1,
        "o3": 3,
        "co": 10,
        "h": 20,
        "no2": 30,
        "p": 40,
        "pm10": 50,
        "pm25": 60,
        "so2": 70,
        "t": 80,
        "w": 90,
    }
    db.insert_into_aqi(conn, qdata)
    r = flask_test_client.get("/api/v1/air_quality")
    data = r.json
    # logger.debug("data=%s",data)
    for k, v in data["no2"]:
        # logger.debug("k=%s v=%s",k,v)
        if k == now and v == 30:
            return
    raise RuntimeError(f"No row matching {qdata} in {data}")
