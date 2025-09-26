"""
Runs every minute to get temperature and fan speeds
"""
import sys
import logging
from os.path import dirname,abspath


# runner is first to run so it needs to add . to the path
sys.path.append(dirname(dirname(abspath(__file__))))

import app.db as db


logger = logging.getLogger(__name__)

def setup_parser():
    import argparse
    parser = argparse.ArgumentParser(description='BasisTech LLC Fixer.',
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    return parser

def main():
    logger.info("%s %s",__file__," ".join(sys.argv))
    parser = setup_parser()
    args = parser.parse_args()
    logger.info("args=%s",args)
    conn = db.get_db_connection()

    c = conn.cursor()
    c2 = conn.cursor()
    c.execute("SELECT * from devices where device_name like 'OFFLINE%'")
    for dev in c.fetchall():
        d2 = dev['device_name'].replace("OFFLINE - ","")
        c2.execute("SELECT device_id from devices where device_name=?",(d2,))
        n2 = c2.fetchone()[0]
        print(dict(dev),n2)
        c2.execute("UPDATE devlog set device_id=? where device_id=?",(n2,dev['device_id']))
    conn.commit()

if __name__=="__main__":
    main()
