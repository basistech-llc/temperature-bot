"""
Run the rules engine
"""
from os.path import join
import time
import logging
from .paths import ROOT_DIR
from . import db
from . import ae200
from .db import SpeedControl

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

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

def get_rules():
    with open( join(ROOT_DIR,'bin','rules.py'), 'r') as f:
        return f.read()

def set_body_speed(conn, body: SpeedControl, addr, agent):
    unit = db.get_ae200_unit(conn, body.device_id)
    db.insert_changelog(conn, addr, device_id=body.device_id, ae200_device_id=unit, new_value=str(body.speed), agent=agent)
    ae200.set_fan_speed(unit, body.speed)
    data = ae200.get_device_info(unit)
    temp = data.get('InletTemp', None)
    db.insert_devlog_entry(conn, device_id=body.device_id, temp=temp, statusdict=data)
    return {'unit':unit, 'temp':temp, 'device_id':body.device_id, 'speed':body.speed}


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
    """Run the rules now and returns the results"""
    logger.debug("when=%s",when)

    def set_fan(device_id, speed):
        set_body_speed(conn, SpeedControl(device_id=device_id, speed=speed), 'n/a', 'rule')

    v1 = {**get_devices_dict(conn), **get_time_dict(when)}
    v2 = {'set_fan': set_fan}
    exec(get_rules(), v1, v2)   # pylint: disable=exec-used
