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
from os.path import dirname,abspath
import tabulate


# runner is first to run so it needs to add . to the path
sys.path.append(dirname(dirname(abspath(__file__))))

from app.paths import DB_PATH,ETC_DIR
from app.rules_engine import run_rules
import app.ae200 as ae200
import app.db as db
import app.hubitat as hubitat

import lib.ctools.clogging as clogging
import lib.ctools.lock as clock

def update_from_ae200(conn, dry_run=False):
    d = ae200.AE200Functions()
    devs = d.getDevices()
    for dev in devs:
        data = d.getDeviceInfo(dev['id'])
        data['id'] = dev['id']
        temp = data.get("InletTemp",None)
        if not dry_run:
            device_id = db.update_devlog_map(conn, device_name=dev['name'], ae200_device_id=dev['id'])
            db.insert_devlog_entry(conn, device_id=device_id, temp=temp, statusdict=data)
        else:
            print(dev,data)

def update_from_hubitat(conn, dry_run=False):
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
    :param conn: database connection
    :param when: datetime of the day to do it for
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
        logging.info("Found an entry on %s with duration=%s",time.asctime(time.localtime(row['logtime'])), row['duration'])
        combine_temp_measurements(conn, prev_week_start, prev_week_end, 5*60)

    # See if there are any in the previous month that need to be
    def prev_month(when):
        pm_year  = when.year
        pm_month = when.month - 1
        if pm_month <= 0:
            pm_month += 12
            pm_year -= 1
        return datetime.datetime(year=pm_year, month=pm_month, day=1)

    prev_month_start = prev_month(prev_month(prev_month(when))).timestamp()
    prev_month_end   = prev_month(prev_month(when)).timestamp()
    c.execute("""select logtime,duration from devlog where logtime>=? and logtime <=? and duration<600 limit 1""",
              (prev_month_start, prev_month_end))
    row = c.fetchone()
    if row:
        logging.info("Found an entry on %s with duration=%s",time.asctime(time.localtime(row['logtime'])), row['duration'])
        combine_temp_measurements(conn, prev_month_start, prev_month_end, 20*60)


def load_csv(conn, fname, after_str, unsafe=False):
    """Loads CSV with reduced durabilty."""
    with open(os.path.join(ETC_DIR,'sample_hubitat.json')) as f:
        hub = json.load(f)
    labelmap = { h['label']:h['name'] for h in hub}
    after = datetime.datetime.fromisoformat(after_str+" 23:59:59")
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
                for label,val in row.items():
                    if label.lower()=='time':
                        when = val
                        dt = datetime.datetime.fromisoformat(val)
                        if dt < after:
                            break # abort for loop on row
                        if (prev_date is not None) and dt.date() != prev_date.date():
                            print("\n")
                            seconds = int(time.time() - t0)
                            remaining = int((time.time()-start_time) / ( lines/total_lines))
                            if seconds>0:
                                print(f"{count} records in {lines}/{total_lines} lines processed in {seconds} seconds = {int(count/seconds)} records/second. Estimate seconds remaining={remaining}. Completion at {time.asctime(time.localtime(time.time()+remaining))}")
                            daily_cleanup(conn, dt)
                            count = 0
                            t0 = time.time()
                        print(f"\r{when}...  ",flush=True,end='')
                        prev_date = dt
                    else:
                        label = label.replace("OFFLINE - ","")
                        name = labelmap[label]
                        db.insert_devlog_entry(conn, device_name=name, temp=val,
                                               logtime=datetime.datetime.fromisoformat(when).timestamp(),
                                               commit=False)
                        count += 1
                conn.commit()
        except KeyboardInterrupt:
            conn.rollback()
            print("Keyboard interrupt. Last time: ",when)
        finally:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA synchronous=NORMAL;")
            conn.execute("PRAGMA wal_checkpoint(FULL)")

def report(conn):
    os.environ['TZ'] = 'America/New_York'  # ET corresponds to New York timezone
    time.tzset()                           # Apply the timezone change
    c = conn.cursor()
    for query in ["""Select count(*),DATE(logtime,'unixepoch','localtime') as d from devlog group by d order by d""",
                  """Select count(*),strftime('%Y-%m-%d %H', logtime,'unixepoch', 'localtime') as d from devlog where logtime > strftime('%s','now','start of day','-1 day') group by d order by d""",
                  """select datetime(d.logtime,'unixepoch','localtime') as w,device_name,d.duration,(d.temp10x+0.0)/10 as temp from devices left join devlog d on devices.device_id=d.device_id order by logtime desc limit 10"""
                  ]:
        c.execute(query)
        data = c.fetchall()
        print(tabulate.tabulate([dict(x).values() for x in data], data[0].keys()))

def setup_parser():
    import argparse
    parser = argparse.ArgumentParser(description='BasisTech LLC Runner.',
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("--csv", help='load csv file')
    parser.add_argument("--unsafe", help="Run without synchronous mode. Fast, but dangerous", action='store_true')
    parser.add_argument("--dry-run", action='store_true')
    parser.add_argument("--csv-after", help="Date after which to import CSV in YYYY-MM-DD format",default="0000-00-00")
    parser.add_argument("--dbfile", help='path to database file', default=DB_PATH)
    parser.add_argument("--report", help="report on the database", action='store_true')
    parser.add_argument("--syslog", help="log to syslog", action='store_true')
    parser.add_argument("--daily", help='Run the daily cleanup', action='store_true')
    parser.add_argument("--rules", help='Also run the rules engine', action='store_true')
    clogging.add_argument(parser)
    return parser

def main():
    logging.info("%s %s",__file__," ".join(sys.argv))
    parser = setup_parser()
    args = parser.parse_args()
    clogging.setup(args.loglevel, syslog=args.syslog, log_format=clogging.LOG_FORMAT,syslog_format=clogging.YEAR + " " + clogging.SYSLOG_FORMAT)
    if not os.path.exists(args.dbfile):
        raise FileNotFoundError(args.dbfile)
    conn = db.connect_db(args.dbfile)
    if args.dry_run:
        print("=dry run=")
    if args.report:
        report(conn)
        return

    if args.csv:
        load_csv(conn, args.csv, args.csv_after, unsafe=args.unsafe)
        return

    # Normal run
    clock.lock_script()
    if args.daily:
        daily_cleanup(conn, datetime.datetime.now())

    update_from_ae200(conn, dry_run=args.dry_run)
    update_from_hubitat(conn, dry_run=args.dry_run)

    if args.rules:
        run_rules(conn)

if __name__=="__main__":
    main()
