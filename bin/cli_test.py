"""
A small test CLI for debugging

"""
import datetime
from pprint import pprint

import sys
import json
from os.path import dirname, abspath

import flask

# Add the parent directory to the path so we can import app modules
sys.path.append(dirname(dirname(abspath(__file__))))

from app.ae200 import AE200Functions
import app.ae200 as ae200
import app.db as db

import lib.ctools.clogging as clogging
import lib.ctools.lock as clock

def setup_parser():
    import argparse
    parser = argparse.ArgumentParser(description='BasisTech LLC Rules Scheduler.',
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("--debug", action='store_true')
    parser.add_argument("--verbose", action='store_true')
    parser.add_argument("--dry-run", action='store_true')
    clogging.add_argument(parser)
    return parser

def main():
    parser = setup_parser()
    args = parser.parse_args()
    if args.dry_run:
        print("=dry run=")

if __name__=="__main__":
    main()
    conn = db.get_db_connection()
    now = datetime.datetime.now()
    print("AE200 devices:")
    if ae200.AE200_SIMULATOR:
        # Use simulator functions
        pprint(ae200.get_devices())
    else:
        # Use real AE200 device
        d = AE200Functions()
        pprint(d.getDevices())
    print("now=", now)
    print("db.get_all_device_aqi:")
    for row in db.get_all_device_aqi(conn):
        print(json.dumps(row))
