"""
Runs every minute to get temperature and fan speeds
"""
import sys
import os.path
import datetime
import json
import csv
import logging

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

def combine_temp_measurements(conn, start_time, end_time, divisions):
    """
    - let offset = (end_time-start_time)/divisions
    - for each offset period from 0..(divisions-1):
      - Reads all the values in the database for all of the devices
        in the time period start_time+offset*division <= time < start_time+offset*(division+1)
      - compute the average temperature.
      - Delete all of the measurements in the time period
      - Write an entry with the average for the entire time period.

    :param conn: database connection
    :param start_time: unix time_t of start of time period.
    :param end_time: unix time_t of end of time period.
    :param divisions: number of divisions to create
    """
    logging.info("combine_temp_measurements(%s,%s,%s",start_time, end_time, divisions)
    conn.isolation_level = None
    c = conn.cursor()
    offset = (end_time-start_time)/divisions
    for division in range(divisions):
        t0 = start_time + offset * division
        t1 = start_time + offset * (division+1)
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
                          (row['device_id'], t0, offset, row['avgtemp']))
            c.execute("commit")
        except conn.Error:
            c.execute("rollback")
            raise


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

def load_csv(conn, fname):
    """Loads CSV with reduced durabilty."""
    with open(os.path.join(ETC_DIR,'sample_hubitat.json')) as f:
        hub = json.load(f)
    labelmap = { h['label']:h['name'] for h in hub}
    print(labelmap)
    with open(fname) as csvfile:
        reader = csv.DictReader(csvfile)
        when = None
        try:
            conn.execute("PRAGMA journal_mode=OFF;")
            conn.execute("PRAGMA synchronous=OFFL;")
            for row in reader:
                for label,val in row.items():
                    if label.lower()=='time':
                        when = val
                        dt = datetime.datetime.fromisoformat(val)
                        print(when)
                        continue
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
