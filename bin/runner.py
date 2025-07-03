"""
Runs every minute to get temperature and fan speeds
"""
import sys
import os.path
import datetime
import json
import csv
import logging
import time

sys.path.append(".")

from myapp.paths import DEV_DB,ETC_DIR
import myapp.ae200 as ae200
import myapp.db as db
import myapp.hubitat as hubitat

import lib.ctools.clogging as clogging
import lib.ctools.lock as clock

def update_ae200(conn, dry_run=False):
    d = ae200.AE200Functions()
    devs = d.getDevices()
    for dev in devs:
        data = d.getDeviceInfo(dev['id'])
        temp = data.get("InletTemp",None)
        if not dry_run:
            db.insert_devlog_entry(conn, device_name=dev['name'], temp=temp, statusdict=data)
        else:
            print(dev,data)

def update_hubitat(conn, dry_run=False):
    for item in hubitat.extract_temperatures(hubitat.get_all_devices()):
        if not dry_run:
            db.insert_devlog_entry(conn, device_name=item['name'], temp=item['temperature'])
        else:
            print(item)

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
    logging.info("combine_temp_measurements(%s,%s,%s",start_time, end_time, seconds)
    conn.isolation_level = None
    c = conn.cursor()
    while True:
        c.execute("SELECT log_id,logtime,duration from devlog where logtime >= ? and logtime < ? and duration < ? LIMIT 1",
                  (start_time, end_time, seconds))
        r = c.fetchone()
        if not r:
            return
        logging.debug("%s",dict(r))
        slot = (r['logtime']-start_time) / seconds
        t0 = start_time + seconds * slot
        t1 = start_time + seconds * (slot+1)
        c.execute("begin")
        try:
            c.execute("""
            SELECT device_id, sum(duration * temp10x)/sum(duration) as avgtemp
            FROM devlog WHERE logtime >= ? and logtime < ? GROUP BY device_id """, (t0,t1))
            rows = c.fetchall()
            c.execute("DELETE FROM devlog WHERE logtime >= ? and logtime < ? """, (t0,t1))
            for row in rows:
                logging.debug("%s",dict(row))
                c.execute("INSERT INTO devlog (device_id,logtime,duration,temp10x) VALUES (?,?,?,?)",
                          (row['device_id'], t0, seconds, row['avgtemp']))
            c.execute("commit")
        except conn.Error:
            c.execute("rollback")
            raise

def daily_cleanup(conn, when):
    """Every day:
    1. Temperatures for the previous week get coarsened to every 5 minutes.
    2. Temperatures for the previous month get coarsened to every 20 minutes.
    """
    print("Daily cleanup")
    c = conn.cursor()

    # See if there are any in the previous week that need to be
    prev_week_start = (when - datetime.timedelta(weeks=2)).timestamp()
    prev_week_end = (when - datetime.timedelta(weeks=1)).timestamp()
    c.execute("""select logtime,duration from devlog where logtime>=? and logtime <=? and duration<600 limit 1""",
              (prev_week_start, prev_week_end))
    row = c.fetchone()
    if row:
        logging.info("Found an entry on %s with duration=%s",time.asctime(time.locatltime(row['logtime'])), row['duration'])
        combine_temp_measurements(conn, prev_week_start, prev_week_end, 5*60)

    # See if there are any in the previous month that need to be
    prev_month_start = (when - datetime.timedelta(months=2)).timestamp()
    prev_month_end = (when - datetime.timedelta(months=1)).timestamp()
    c.execute("""select logtime,duration from devlog where logtime>=? and logtime <=? and duration<600 limit 1""",
              (prev_month_start, prev_month_end))
    row = c.fetchone()
    if row:
        logging.info("Found an entry on %s with duration=%s",time.asctime(time.locatltime(row['logtime'])), row['duration'])
        combine_temp_measurements(conn, prev_month_start, prev_month_end, 20*60)



def load_csv(conn, fname):
    """Loads CSV with reduced durabilty."""
    with open(os.path.join(ETC_DIR,'sample_hubitat.json')) as f:
        hub = json.load(f)
    labelmap = { h['label']:h['name'] for h in hub}
    print(labelmap)
    with open(fname) as csvfile:
        reader = csv.DictReader(csvfile)
        when = None
        prev_date = None
        try:
            conn.execute("PRAGMA journal_mode=OFF;")
            conn.execute("PRAGMA synchronous=OFF;")
            for row in reader:
                for label,val in row.items():
                    if label.lower()=='time':
                        when = val
                        dt = datetime.datetime.fromisoformat(val)
                        print(when)
                        if (prev_date is not None) and dt.date() != prev_date.date():
                            daily_cleanup(dt)
                        prev_date = dt
                    else:
                        label = label.replace("OFFLINE - ","")
                        name = labelmap[label]
                        db.insert_devlog_entry(conn, device_name=name, temp=val,
                                               logtime=datetime.datetime.fromisoformat(when).timestamp(),
                                               commit=False)
                conn.commit()
        except KeyboardInterrupt:
            print("Keyboard interrupt. Last time: ",when)
        finally:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA synchronous=NORMAL;")
            conn.execute("PRAGMA wal_checkpoint(FULL)")

def setup_parser():
    import argparse
    parser = argparse.ArgumentParser(description='BasisTech LLC Runner.',
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("--debug", action='store_true')
    parser.add_argument("--csv", help='load csv file')
    parser.add_argument("--dry-run", action='store_true')
    parser.add_argument("--dbfile", help='path to database file', default=DEV_DB)
    clogging.add_argument(parser)
    return parser

def main():
    parser = setup_parser()
    args = parser.parse_args()
    clock.lock_script()
    if not os.path.exists(args.dbfile):
        raise FileNotFoundError(args.dbfile)
    conn = db.connect_db(args.dbfile)
    if args.csv:
        load_csv(conn,args.csv)
    if args.dry_run:
        print("=dry run=")
    update_ae200(conn, dry_run=args.dry_run)
    update_hubitat(conn, dry_run=args.dry_run)

if __name__=="__main__":
    main()
