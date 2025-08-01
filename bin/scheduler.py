"""
Runs every minute to implement rules.
"""
import datetime
import json
from pprint import pprint

import app.ae200 as ae200
from app.ae200 import AE200Functions, AE200_ADDRESS

import lib.ctools.clogging as clogging
import lib.ctools.lock as clock

address = AE200_ADDRESS

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
    clock.lock_script()
    if args.dry_run:
        print("=dry run=")

if __name__=="__main__":
    main()
    now = datetime.datetime.now()
    d = AE200Functions()
    pprint(d.getDevices(address))
    print("now=", now)
    print("are 51 status:")
    print(json.dumps(ae200.get_dev_status(2), indent=4))
