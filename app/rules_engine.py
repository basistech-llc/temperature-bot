"""
Run the rules engine
"""
import json
from os.path import join
import time
import logging

from flask import request


from .paths import ROOT_DIR
from . import db
from . import ae200
from .db import SpeedControl

logger = logging.getLogger(__name__)

RULES_DEVICE_NAME = 'rules_engine'

def rules_id(conn):
    return  db.get_or_create_device_id(conn, RULES_DEVICE_NAME)

def get_devices_dict(conn):
    """Add all of the devices in the devices table to the global environment"""
    c = conn.cursor()
    c.execute("SELECT * from devices order by device_name")
    ret = {dev['device_name'].replace(' ','_').upper() : dev['device_id'] for dev in c.fetchall()}
    logging.debug("ret=%s",ret)
    return ret

def get_time_dict(when=None):
    if when is None:
        when = time.time()
    tm = time.localtime(when)
    return {'YEAR':tm.tm_year, 'MONTH':tm.tm_mon, 'MDAY':tm.tm_mday, 'HOUR':tm.tm_hour, 'MIN':tm.tm_min, 'SEC':tm.tm_sec,
            'WDAY':tm.tm_wday, 'YDAY':tm.tm_yday, 'DST':tm.tm_isdst,
            'MONDAY':tm.tm_wday==0,
            'TUESDAY':tm.tm_wday==1,
            'WEDNESDAY':tm.tm_wday==2,
            'THURSDAY':tm.tm_wday==3,
            'FRIDAY':tm.tm_wday==4,
            'SATURDAY':tm.tm_wday==5,
            'SUNDAY':tm.tm_wday==6,
            'AM':tm.tm_hour<12,
            'PM':tm.tm_hour>=12 }

def rules_disabled_until(conn):
    """Rules are enabled by default. They are disabled if the last changelog entry for the rules device specifies a disable time in the new_value text"""
    c = conn.cursor()
    c.execute("SELECT * from changelog where device_id=? order by changelog_id DESC LIMIT 1",(rules_id(conn),))
    row = c.fetchone()
    if row is None:
        logging.debug("rules_disabled_until row is None")
        return 0
    until_time = json.loads(row['new_value']).get('seconds',0) + row['logtime']
    logging.debug("rules_disabled_until row=%s until_time=%s device_id=%s",dict(row),until_time,rules_id(conn))
    if until_time < time.time():
        return 0
    return until_time


def disable_rules(conn,seconds:int):
    """Enter a database engtry to disable the rules until a specific time."""
    if seconds==0:
        msg = json.dumps({'comment':'enable rules', 'seconds':seconds})
    else:
        asc_when = time.asctime(time.localtime(time.time()+seconds))
        msg = json.dumps({'comment':f'disable rules until {asc_when}',
                          'seconds':seconds})
    logging.debug("disable_rules(seconds=%s,msg=%s,device_id=%s)",seconds,msg,rules_id(conn))
    c = conn.cursor()
    c.execute("INSERT INTO changelog (logtime, ipaddr, device_id, new_value) VALUES (?,?,?,?)",
              (time.time(), request.remote_addr, rules_id(conn), msg))
    conn.commit()
    logging.debug("rules_disabled_until=%s",rules_disabled_until(conn))


def get_rules():
    with open( join(ROOT_DIR,'bin','rules.py'), 'r') as f:
        return f.read()

def set_body_speed(conn, body: SpeedControl, ipaddr, agent):
    """
    :param conn: SQLIte3 database conneciton
    :param body: Unit to set, and new speed
    :param ipaddr: Who requested the change
    :param agent: What requested the change.
    """

    unit_id = db.get_ae200_unit(conn, body.device_id)

    # Get the current speed of the unit
    current_speed = ae200.get_device_speed(unit_id)
    if current_speed==body.speed:
        logger.info("set_body_speed body=[%s] ipaddr=%s agent=%s. Speed will not change",body,ipaddr,agent)
    else:
        logger.info("set_body_speed body=[%s] ipaddr=%s agent=%s. Speed changed. current_speed=%s",body,ipaddr,agent,current_speed)
        db.insert_changelog(conn, ipaddr=ipaddr, device_id=body.device_id, ae200_device_id=unit_id,
                            current_values=str(current_speed), new_value=str(body.speed), agent=agent)
        ae200.set_fan_speed(unit_id, body.speed)
    data = ae200.get_device_info(unit_id)
    temp = data.get('InletTemp', None)
    db.insert_devlog_entry(conn, device_id=body.device_id, temp=temp, statusdict=data)
    return {'unit':unit_id, 'temp':temp, 'device_id':body.device_id, 'speed':body.speed}


def rules_results(conn, when=None):
    """Reports what would happen if the rules were run at `when`"""
    logger.debug("when=%s",when)

    results = []
    def set_fan_verbose(device_id, value):
        results.append(f"Fan {device_id} set to {value}\n")

    v1 = {**get_devices_dict(conn), **get_time_dict(when)}
    v2 = {'set_fan': set_fan_verbose}
    exec(get_rules(), v1, v2)   # pylint: disable=exec-used
    return "\n".join(results)

def run_rules(conn, when=None):
    """Run the rules now and returns the results.
    Note: runs rules even if they are disabled. That has to be decided elsewhere.
    """
    logger.debug("when=%s",when)

    def set_fan(device_id, speed):
        set_body_speed(conn, SpeedControl(device_id=device_id, speed=speed), 'n/a', 'rule')

    v1 = {**get_devices_dict(conn), **get_time_dict(when)}
    v2 = {'set_fan': set_fan}
    exec(get_rules(), v1, v2)   # pylint: disable=exec-used
