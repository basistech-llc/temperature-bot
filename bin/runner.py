"""
Runs every minute to get temperature and fan speeds
"""
import sys
import os.path
#import datetime
#import json

sys.path.append(".")

from myapp.paths import DEV_DB
import myapp.ae200 as ae200
import myapp.db as db
import myapp.hubitat as hubitat

import lib.ctools.clogging as clogging
import lib.ctools.lock as clock

def setup_parser():
    import argparse
    parser = argparse.ArgumentParser(description='BasisTech LLC Runner.',
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("--debug", action='store_true')
    parser.add_argument("--dry-run", action='store_true')
    parser.add_argument("--dbfile", help='path to database file', default=DEV_DB)
    clogging.add_argument(parser)
    return parser

def update_ae200(conn, dry_run=False):
    d = ae200.AE200Functions()
    devs = d.getDevices()
    for dev in devs:
        data = d.getDeviceInfo(dev['id'])
        if not dry_run:
            db.insert_devlog_entry(conn, device_name=dev['name'], statusdict=data)
        else:
            print(dev,data)


def update_hubitat(conn, dry_run=False):
    for item in hubitat.extract_temperatures(hubitat.get_all_devices()):
        if not dry_run:
            db.insert_devlog_entry(conn, device_name=item['name'], temp=item['temperature'])
        else:
            print(item)



def main():
    parser = setup_parser()
    args = parser.parse_args()
    clock.lock_script()
    if not os.path.exists(args.dbfile):
        raise FileNotFoundError(args.dbfile)
    conn = db.connect_db(args.dbfile)
    if args.dry_run:
        print("=dry run=")
    update_ae200(conn, dry_run=args.dry_run)
    update_hubitat(conn, dry_run=args.dry_run)

if __name__=="__main__":
    main()
