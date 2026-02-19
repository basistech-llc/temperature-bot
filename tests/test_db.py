"""
test for db.py
"""

import logging
import json
import types

from app import db
from bin import runner


logger = logging.getLogger(__name__)

def test_temperature_insert(test_database_conn_with_test_data):
    conn = test_database_conn_with_test_data[0]

    # Clear out the devlog
    c = conn.cursor()
    c.execute("delete from devlog")
    conn.commit()

    db.insert_devlog_entry(conn, device_name="devtest1", temp=20, logtime=100)
    db.insert_devlog_entry(conn, device_name="devtest1", temp=20, logtime=101) # extends first measurement by 1 second to 2 seconds
    db.insert_devlog_entry(conn, device_name="devtest1", temp=20, logtime=112) # extends first measurement by another 11 seconds to 13 seconds

    db.insert_devlog_entry(conn, device_name="devtest2", temp=20, logtime=100)
    db.insert_devlog_entry(conn, device_name="devtest2", temp=21, logtime=111) # new measurement. We now have two measurements with 1 second each.
    db.insert_devlog_entry(conn, device_name="devtest2", temp=22, logtime=112) # new measurement. We have no idea when when the measurement changes.
                                                                      # We have 3 measurements, 1 second each

    dev1_id = db.get_or_create_device_id(conn, "devtest1")
    dev2_id = db.get_or_create_device_id(conn, "devtest2")
    assert dev1_id != dev2_id

    c = conn.cursor()
    c.execute("SELECT *,dn.device_name as device_name from devlog d1 INNER JOIN (select device_id,MAX(logtime) as max_logtime from devlog group by device_id) as d2 on d1.device_id = d2.device_id and d1.logtime = d2.max_logtime INNER JOIN devices dn on d1.device_id = dn.device_id")
    rows = c.fetchall()
    assert len(rows)==2
    assert rows[0]['device_name'] == 'devtest1'
    assert rows[0]['temp10x'] == 200
    assert rows[0]['logtime'] == 100
    assert rows[0]['duration'] == 13
    devtest1_id = rows[0]['device_id']

    assert rows[1]['device_name'] == 'devtest2'
    assert rows[1]['temp10x'] == 220
    assert rows[1]['logtime'] == 112
    assert rows[1]['duration'] == 1
    devtest2_id = rows[1]['device_id']

    # make sure status_json behaves as expected
    db.insert_devlog_entry(conn, device_name="complex1", statusdict={'name':'foo', 'val':'bar'}, logtime=100)
    db.insert_devlog_entry(conn, device_name="complex1", statusdict={'name':'foo', 'val':'bar2'}, logtime=101)
    db.insert_devlog_entry(conn, device_name="complex1", statusdict={'name':'foo', 'val':'bar2'}, logtime=102)
    c.execute("SELECT * from devlog where device_id=(select device_id from devices where device_name='complex1') order by logtime DESC limit 1")
    rows = c.fetchall()
    assert len(rows)==1
    assert json.loads(rows[0]['status_json']) == {'name':'foo', 'val' : 'bar2'}

    # finally, check to see if our combining code broadly works
    logging.debug("devtest1_id=%s",devtest1_id)
    runner.combine_temp_measurements(conn,100,150,50)
    c.execute("SELECT * from devlog where device_id=?",(devtest1_id,))
    rows = c.fetchall()
    assert len(rows)==1
    assert rows[0]['logtime']==100
    assert rows[0]['duration']==50
    assert rows[0]['temp10x']==200 # temperature never changed from 20

    c.execute("SELECT * from devlog where device_id=?",(devtest2_id,))
    rows = c.fetchall()
    assert len(rows)==1
    assert rows[0]['logtime']==100
    assert rows[0]['duration']==50
    assert rows[0]['temp10x']==210 # 1 seconds at 20, 1 second at 21, 1 second at 22
