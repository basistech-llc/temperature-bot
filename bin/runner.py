"""
Runs every minute by cron.
 - gets temperature and writes to database
 - runs rules engine
"""

import sys
import os.path
import datetime
import json
import csv
import logging
import time
from os.path import dirname, abspath
import tabulate
import requests

# runner is first to run so it needs to add . to the path
sys.path.append(dirname(dirname(abspath(__file__))))

from app.paths import ETC_DIR
from app.rules_engine import rules_results, run_rules
from app import airquality
from app import ae200
from app import airthings
from app import db
from app import db_alerts
from app import hubitat
from app.device_types import (
    DEVICE_TYPE_SENSOR,
    HubitatDevice,
    classify_hubitat_device,
)
from app import rules_engine


import lib.ctools.lock as clock
import lib.ctools.clogging as clogging

logger = logging.getLogger(__name__)


def update_from_ae200(conn):
    if ae200.AE200_SIMULATOR:
        # Use simulator functions
        devs = ae200.get_devices()
        for dev in devs:
            data = ae200.get_device_info(dev["id"])
            process_device_alert_data(conn, dev, data)
    else:
        # Use real AE200 device
        d = ae200.AE200Functions()
        devs = d.getDevices()
        for dev in devs:
            data = d.getDeviceInfo(dev["id"])
            process_device_alert_data(conn, dev, data)


def process_device_alert_data(conn, dev, data):
    """Process device data for both temperature logging and alert collection."""
    # [TODO] Need to add synthetic alert data to simulator
    data["id"] = dev["id"]
    temp = data.get("InletTemp", None)
    device_id = db.update_devlog_map(
        conn, device_name=dev["name"], ae200_device_id=dev["id"]
    )

    # Extract alert fields
    for alert_type in ["ErrorSign", "FilterSign", "CheckWater"]:
        if alert_type in data:
            db_alerts.insert_or_update_alert(
                conn,
                device_id=device_id,
                alert_type=alert_type,
                alert_value=data[alert_type],
            )

    db.insert_devlog_entry(conn, device_id=device_id, temp=temp, statusdict=data)


def update_from_hubitat(conn):
    try:
        devices = hubitat.get_all_devices()
        typed_devices = [HubitatDevice.model_validate(item) for item in devices]
        temps = hubitat.extract_temperatures(devices)
    except requests.exceptions.RequestException as e:
        logger.error("update_from_hubitat: request failed: %s", e)
        return
    except RuntimeError as e:
        logger.error("update_from_hubitat: %s", e)
        return
    device_ids: dict[str, int] = {}
    observed_at = int(time.time())
    for device, raw_device in zip(typed_devices, devices):
        device_type, _evidence = classify_hubitat_device(device)
        device_id = db.get_or_create_device_id(
            conn, device.name, device_type=device_type
        )
        device_ids[device.name] = device_id
        motion = (raw_device.get("attributes") or {}).get("motion")
        if motion in {"active", "inactive"}:
            db.record_presence_observation(
                conn,
                device_id=device_id,
                present=motion == "active",
                observed_at=observed_at,
            )
    updated_names = []
    for item in temps:
        statusdict = item.get("status") or {}
        db.insert_devlog_entry(
            conn,
            device_id=device_ids[item["name"]],
            temp=item["temperature"],
            statusdict=statusdict,
        )
        updated_names.append(item["name"])
    logger.info(
        "update_from_hubitat: updated %d temperature devices: %s",
        len(updated_names),
        ", ".join(updated_names),
    )

def update_from_airthings(conn):
    logtime = time.time()
    data = airthings.read_airthings_now()
    updated_names = []
    for dev in data:
        sensors = {sensor['sensorType']:{'value':sensor['value'],'unit':sensor['unit']} for sensor in dev['sensors']}
        name = "Airthings "+dev['name']
        temp = sensors['temp']['value']
        if conn is None:
            print("name=",name,"temp=",temp,'status',sensors)
            continue
        db.get_or_create_device_id(conn, name, device_type=DEVICE_TYPE_SENSOR)
        db.insert_devlog_entry(conn, device_name=name, temp=temp, statusdict=sensors, logtime=logtime)
        updated_names.append(name)
    if conn is not None:
        logger.info(
            "update_from_airthings: updated %d devices: %s",
            len(updated_names),
            ", ".join(updated_names),
        )


def update_aqi(conn):
    data = airquality.get_aqi_aqicn_full()
    values = {
        k: data["iaqi"][k]["v"]
        for k in ["co", "h", "no2", "o3", "p", "pm10", "pm25", "so2", "t", "w"]
    }
    values["aqi"] = data["aqi"]
    values["logtime"] = int(time.time())
    db.insert_into_aqi(conn, values)


def combine_temp_measurements(conn, start_time, end_time, seconds):
    """
      - find the time of the first entry in the database after start_time that is shorter than 'seconds'
      - determine which slot it is (where slots are defined as seconds-sized slots after start_time)
      - Reads all the values in the database for all of the devices
        in the time period start_time+seconds*slot <= time < start_time+seconds*(slot+1)
      - compute the average temperature.
      - Delete all of the measurements in the time period
      - Write an entry with the average for the entire time period.

    :param conn: database connection
    :param start_time: unix time_t of start of time period.
    :param end_time: unix time_t of end of time period.
    :param divisions: number of divisions to create
    """
    if seconds > db.MAX_DURATION:
        raise ValueError(
            f"combine_temp_measurements seconds={seconds} exceeds "
            f"MAX_DURATION={db.MAX_DURATION}"
        )

    logger.info("combine_temp_measurements(%s,%s,%s", start_time, end_time, seconds)
    conn.isolation_level = None
    c = conn.cursor()
    while True:
        c.execute(
            "SELECT log_id,logtime,duration from devlog where logtime >= ? and logtime < ? and duration < ? LIMIT 1",
            (start_time, end_time, seconds),
        )
        r = c.fetchone()
        if not r:
            return
        logger.debug("%s", dict(r))
        slot = (r["logtime"] - start_time) / seconds
        t0 = start_time + seconds * slot
        t1 = start_time + seconds * (slot + 1)
        c.execute("begin")
        try:
            c.execute(
                """
            SELECT device_id, sum(duration * temp10x)/sum(duration) as avgtemp
            FROM devlog WHERE logtime >= ? and logtime < ? GROUP BY device_id """,
                (t0, t1),
            )
            rows = c.fetchall()
            c.execute(
                "DELETE FROM devlog WHERE logtime >= ? and logtime < ? ", (t0, t1)
            )
            for row in rows:
                logger.debug("%s", dict(row))
                c.execute(
                    "INSERT INTO devlog (device_id,logtime,duration,temp10x) VALUES (?,?,?,?)",
                    (row["device_id"], t0, seconds, row["avgtemp"]),
                )
            c.execute("commit")
        except conn.Error:
            c.execute("rollback")
            raise


def daily_cleanup(conn, when):
    """Every day:
    1. Temperatures for the previous week get coarsened to every 5 minutes.
    2. Temperatures for the previous month get coarsened to every 20 minutes.
    :param conn: database connection
    :param when: datetime of the day to do it for
    """
    print("Daily cleanup")
    c = conn.cursor()

    # See if there are any in the previous week that need to be
    prev_week_start = (when - datetime.timedelta(weeks=2)).timestamp()
    prev_week_end = (when - datetime.timedelta(weeks=1)).timestamp()
    c.execute(
        """select logtime,duration from devlog where logtime>=? and logtime <=? and duration<600 limit 1""",
        (prev_week_start, prev_week_end),
    )
    row = c.fetchone()
    if row:
        logger.info(
            "Found an entry on %s with duration=%s",
            time.asctime(time.localtime(row["logtime"])),
            row["duration"],
        )
        combine_temp_measurements(conn, prev_week_start, prev_week_end, 5 * 60)

    # See if there are any in the previous month that need to be
    def prev_month(when):
        pm_year = when.year
        pm_month = when.month - 1
        if pm_month <= 0:
            pm_month += 12
            pm_year -= 1
        return datetime.datetime(year=pm_year, month=pm_month, day=1)

    prev_month_start = prev_month(prev_month(prev_month(when))).timestamp()
    prev_month_end = prev_month(prev_month(when)).timestamp()
    c.execute(
        """select logtime,duration from devlog where logtime>=? and logtime <=? and duration<600 limit 1""",
        (prev_month_start, prev_month_end),
    )
    row = c.fetchone()
    if row:
        logger.info(
            "Found an entry on %s with duration=%s",
            time.asctime(time.localtime(row["logtime"])),
            row["duration"],
        )
        combine_temp_measurements(conn, prev_month_start, prev_month_end, 20 * 60)


def load_csv(conn, fname, after_str, unsafe=False):
    """Loads CSV with reduced durabilty."""
    with open(os.path.join(ETC_DIR, "sample_hubitat.json")) as f:
        hub = json.load(f)
    labelmap = {h["label"]: h["name"] for h in hub}
    after = datetime.datetime.fromisoformat(after_str + " 23:59:59")
    with open(fname) as csvfile:
        total_lines = csvfile.read().count("\n")
        lines = 0
        start_time = time.time()
        csvfile.seek(0)
        reader = csv.DictReader(csvfile)
        when = None
        prev_date = None
        try:
            if unsafe:
                conn.execute("PRAGMA journal_mode=OFF;")
                conn.execute("PRAGMA synchronous=OFF;")
            else:
                conn.execute("PRAGMA journal_mode=WALL;")
                conn.execute("PRAGMA synchronous=NORMAL;")
            t0 = time.time()
            count = 0
            for row in reader:
                lines += 1
                for label, val in row.items():
                    if label.lower() == "time":
                        when = val
                        dt = datetime.datetime.fromisoformat(val)
                        if dt < after:
                            break  # abort for loop on row
                        if (prev_date is not None) and dt.date() != prev_date.date():
                            print("\n")
                            seconds = int(time.time() - t0)
                            remaining = int(
                                (time.time() - start_time) / (lines / total_lines)
                            )
                            if seconds > 0:
                                print(
                                    f"{count} records in {lines}/{total_lines} lines processed in {seconds} seconds = {int(count / seconds)} records/second. Estimate seconds remaining={remaining}. Completion at {time.asctime(time.localtime(time.time() + remaining))}"
                                )
                            daily_cleanup(conn, dt)
                            count = 0
                            t0 = time.time()
                        print(f"\r{when}...  ", flush=True, end="")
                        prev_date = dt
                    else:
                        label = label.replace("OFFLINE - ", "")
                        name = labelmap[label]
                        db.insert_devlog_entry(
                            conn,
                            device_name=name,
                            temp=val,
                            logtime=datetime.datetime.fromisoformat(when).timestamp(),
                            commit=False,
                        )
                        count += 1
                conn.commit()
        except KeyboardInterrupt:
            conn.rollback()
            print("Keyboard interrupt. Last time: ", when)
        finally:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA synchronous=NORMAL;")
            conn.execute("PRAGMA wal_checkpoint(FULL)")


def report(conn):
    os.environ["TZ"] = "America/New_York"  # ET corresponds to New York timezone
    time.tzset()  # Apply the timezone change
    c = conn.cursor()
    for query in [
        """Select count(*),DATE(logtime,'unixepoch','localtime') as d from devlog group by d order by d""",
        """Select count(*),strftime('%Y-%m-%d %H', logtime,'unixepoch', 'localtime') as d from devlog where logtime > strftime('%s','now','start of day','-1 day') group by d order by d""",
        """select datetime(d.logtime,'unixepoch','localtime') as w,device_name,d.duration,(d.temp10x+0.0)/10 as temp from devices left join devlog d on devices.device_id=d.device_id order by logtime desc limit 10""",
    ]:
        c.execute(query)
        data = c.fetchall()
        if data:
            print(tabulate.tabulate([dict(x).values() for x in data], data[0].keys()))
        else:
            print("No data found")


def setup_parser():
    import argparse

    parser = argparse.ArgumentParser(
        description="BasisTech LLC Runner.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--csv", help="load csv file")
    parser.add_argument(
        "--unsafe",
        help="Run without synchronous mode. Fast, but dangerous",
        action="store_true",
    )
    parser.add_argument(
        "--csv-after",
        help="Date after which to import CSV in YYYY-MM-DD format",
        default="0000-00-00",
    )
    parser.add_argument("--report", help="report on the database", action="store_true")
    parser.add_argument("--syslog", help="log to syslog", action="store_true")
    parser.add_argument("--daily", help="Run the daily cleanup", action="store_true")
    parser.add_argument(
        "--rules",
        choices=["test", "run", "prune"],
        help="Just run the rules engine.",
    )
    parser.add_argument("--aqi", help="Save AQI to database", action="store_true")
    parser.add_argument("--airthings", help="debug the airthings", action="store_true")
    clogging.add_argument(parser)
    return parser


def main():
    logger.info("%s %s", __file__, " ".join(sys.argv))
    parser = setup_parser()
    args = parser.parse_args()
    clogging.setup(
        args.loglevel,
        syslog=True,
        filename=args.logfilename,
        log_format=clogging.LOG_FORMAT,
        syslog_format=clogging.YEAR + " " + clogging.SYSLOG_FORMAT,
    )
    if args.airthings:
        update_from_airthings(None)
        sys.exit(0)

    conn = db.get_db_connection()
    if args.report:
        report(conn)
    elif args.csv:
        load_csv(conn, args.csv, args.csv_after, unsafe=args.unsafe)
    elif args.aqi:
        update_aqi(conn)
    elif args.daily:
        daily_cleanup(conn, datetime.datetime.now())
    elif args.rules:
        if args.rules == "prune":
            rules_engine.prune_rules(conn)
        else:
            res = rules_engine.run_rules(conn, commit=(args.rules == "run"))
            print(res)
    else:
        # Run everything
        clock.lock_script(abspath(__file__))
        update_from_ae200(conn)
        update_from_hubitat(conn)
        update_from_airthings(conn)
        if not db.get_rules_master_enabled(conn):
            logger.info("Master rules switch is OFF; skipping all rules execution")
        else:
            run_rules(conn, commit=1)


if __name__ == "__main__":
    main()
