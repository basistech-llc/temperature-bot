"""
Run the rules engine.

The RULES_ENGINE is a special device which, if disabled, disables all rules.
Each individual rule can also be disabled.

"""
from os.path import join
import time
import logging


from .paths import ROOT_DIR
from . import db
from . import ae200
from .db import SpeedControl,DriveControl

logger = logging.getLogger(__name__)

RULES_DEVICE_NAME = 'rules_engine'

def rules_id(conn):
    return  db.get_or_create_device_id(conn, RULES_DEVICE_NAME)

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

def all_rules_disabled_until(conn) -> int:
    until = db.device_rules_disabled_until(conn, rules_id(conn))
    logging.info("all rules disabled until %s",until)
    return until if until else 0

def disable_all_rules(conn, seconds:int):
    """Enter a database engtry to disable the rules for a period of seconds.
    :param seconds: how long to disable rules for
    """
    logging.info("disable_all_rules(%s)",seconds)
    db.disable_rules_for_device(conn, rules_id(conn), seconds)

def get_rules():
    with open( join(ROOT_DIR,'bin','rules.py'), 'r') as f:
        return f.read()

def prune_rules(conn):
    now = int(time.time())
    c = conn.cursor()
    c.execute("update devices set disabled_until=0 where disabled_until>0 and disabled_until<?",
              (now,))
    conn.commit()

def set_body_fan_speed(conn, body: SpeedControl, ipaddr, agent):
    """
    :param conn: SQLIte3 database conneciton
    :param body: Unit to set, and new speed
    :param ipaddr: Who requested the change
    :param agent: What requested the change.
    """

    unit_id = db.get_ae200_unit(conn, body.device_id)

    # Get the current speed of the unit
    current_fan_speed = ae200.get_device_fan_speed(unit_id)
    if current_fan_speed==body.fan_speed:
        logger.info("set_body_fan_speed body=[%s] ipaddr=%s agent=%s. Speed will not change",body,ipaddr,agent)
    else:
        logger.info("set_body_fan_speed body=[%s] ipaddr=%s agent=%s. Speed changed. current_fan_speed=%s",body,ipaddr,agent,current_fan_speed)
        db.insert_changelog(conn, ipaddr=ipaddr, device_id=body.device_id, ae200_device_id=unit_id,
                            current_values=str(current_fan_speed), new_value=str(body.fan_speed), agent=agent)
        ae200.set_fan_speed(unit_id, body.fan_speed)
    data = ae200.get_device_info(unit_id)
    temp = data.get('InletTemp', None)
    db.insert_devlog_entry(conn, device_id=body.device_id, temp=temp, statusdict=data)
    return {'unit':unit_id, 'temp':temp, 'device_id':body.device_id, 'speed':body.fan_speed}

def set_body_drive(conn, body: SpeedControl, ipaddr, agent):
    """
    :param conn: SQLIte3 database conneciton
    :param body: Unit to set, and new drive
    :param ipaddr: Who requested the change
    :param agent: What requested the change.
    """
    logger.debug("==== set_body_drive body=%s",body)

    unit_id = db.get_ae200_unit(conn, body.device_id)

    # Get the current speed of the unit
    current_drive = ae200.get_device_drive(unit_id)
    if current_drive==body.drive:
        logger.info("set_body_drive body=[%s] ipaddr=%s agent=%s. Drive will not change",body,ipaddr,agent)
    else:
        logger.info("set_body_drive body=[%s] ipaddr=%s agent=%s. Drive changed. current_drive=%s",body,ipaddr,agent,current_drive)
        db.insert_changelog(conn, ipaddr=ipaddr, device_id=body.device_id, ae200_device_id=unit_id,
                            current_values=str(current_drive), new_value=str(body.drive), agent=agent)
        ae200.set_drive(unit_id, body.drive)
    data = ae200.get_device_info(unit_id)
    temp = data.get('InletTemp', None)
    db.insert_devlog_entry(conn, device_id=body.device_id, temp=temp, statusdict=data)
    return {'unit':unit_id, 'temp':temp, 'device_id':body.device_id, 'drive':body.drive}


def rules_results(conn, when=None, aqi=50):
    """Reports what would happen if the rules were run at `when` with a specific AQI"""
    logger.debug("when=%s",when)

    results = []
    def set_drive_verbose(device_id, value):
        results.append(f"Device {device_id} drive set to {value}")
    def set_fan_speed_verbose(device_id, value):
        results.append(f"Device {device_id} speed set to {value}")

    global_vars = {**db.devices_to_device_id(conn), **get_time_dict(when)}
    global_vars['AQI'] = aqi
    local_vars = {'set_drive': set_drive_verbose, 'set_fan_speed': set_fan_speed_verbose}
    exec(get_rules(), global_vars, local_vars)   # pylint: disable=exec-used
    return "\n".join(results)

def run_rules(conn, when=None):
    """Run the rules now and returns the results.
    Does not execute command if all rules are disabled or if the rules for the sepcific device are disabled
    """
    logger.debug("when=%s",when)

    all_devices = db.fetch_all_device_dicts(conn)
    disabled_until_dict = {dev['device_id']:dev['disabled_until'] for dev in all_devices}
    def is_disabled(device_id):
        try:
            return time.time() > disabled_until_dict.get(device_id,0)
        except (ValueError,TypeError,KeyError):
            return False

    if is_disabled( rules_id( conn ) ):
        logger.info("all rules disabled")

    def set_drive(device_id, drive):
        if is_disabled(device_id):
            logger.info("device_id=%s drive set disabled",(device_id,))
            return
        set_body_drive(conn, DriveControl(device_id=device_id, drive=drive), 'n/a', 'rule')

    def set_fan_speed(device_id, fan_speed):
        if is_disabled(device_id):
            logger.info("device_id=%s fan set disabled",(device_id,))
            return
        set_body_fan_speed(conn, SpeedControl(device_id=device_id, fan_speed=fan_speed), 'n/a', 'rule')

    v1 = {**db.devices_to_device_id(conn), **get_time_dict(when)}
    v1['AQI'] = db.get_last_aqi(conn)
    v2 = {'set_drive': set_drive, 'set_fan_speed':set_fan_speed }
    exec(get_rules(), v1, v2)   # pylint: disable=exec-used

    # finally, if the time has passed for any rule, set to 0
    now = int(time.time())
    for dev in all_devices:
        if 0 < dev['disabled_until'] < now:
            db.disable_rules_for_device(conn, dev['device_id'], 0, agent='rules runner', comment='disabled timer expired')
