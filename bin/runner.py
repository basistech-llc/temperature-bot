"""
Runs every minute to get temperature and fan speeds
"""
import sys
import os.path
import datetime
import json
import csv

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
    with open(os.path.join(ETC_DIR,'sample_hubitat.json')) as f:
        hub = json.load(f)
    labelmap = { h['label']:h['name'] for h in hub}
    print(labelmap)
    with open(fname) as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            for label,val in row.items():
                if label.lower()=='time':
                    dt = datetime.datetime.fromisoformat(val)
                    print(dt,dt.timestamp())
                    continue
                label = label.replace("OFFLINE - ","")
                name = labelmap[label]
                db.insert_devlog_entry(conn, device_name=name, temp=val, logtime=dt.timestamp(), commit=False)
            conn.commit()


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
