"""
test aqi endpoint
"""
import logging
import time

from unittest.mock import patch
from conftest import skip_on_github

from app import airquality
from app import db

logger = logging.getLogger(__name__)

def test_aqi_decode():
    assert airquality.aqi_decode(50) == {'value':50, 'name':'Good', 'color_name':'Green', 'color':'#00e400'}

def test_aqi_rest(flask_test_client, test_database_conn_with_test_data): # noqa: F811
    conn = test_database_conn_with_test_data[0]
    now = int(time.time())+10
    qdata = {'logtime':now, 'aqi':1, 'o3':3, 'co':10, 'h':20, 'no2':30, 'p':40, 'pm10':50, 'pm25':60, 'so2':70, 't':80, 'w':90}
    db.insert_into_aqi(conn, qdata)
    r = flask_test_client.get(f"/api/v1/aqi")
    data = r.json
    for d in data['series']:
        if d['logtime']==now:
            assert d==qdata
            return
    raise RuntimeError(f"No row matching {qdata} in {data}")
