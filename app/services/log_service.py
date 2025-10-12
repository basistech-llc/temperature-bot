"""
Log-related business logic
"""
import logging
from typing import List, Dict, Any
from ..utils.query_utils import temporal_quantification
from ..util import github_style_duration

logger = logging.getLogger(__name__)


class LogService:
    """Service for log-related operations"""

    def __init__(self):
        self.logger = logger

    def get_changelog(self, conn, draw: int = 1, start_row: int = 0, length: int = 100) -> Dict[str, Any]:
        """Get changelog data with pagination"""
        cmd = """SELECT c.logtime, c.ipaddr, d.device_name as unit, c.new_value, c.agent, c.comment FROM changelog c
                   LEFT JOIN devices d ON c.device_id = d.device_id WHERE 1=1"""
        args: List[Any] = []

        (cmd, args) = temporal_quantification(cmd, args)

        cmd += " ORDER BY logtime DESC LIMIT ? OFFSET ?"
        args.extend([length, start_row])
        self.logger.debug("cmd=%s args=%s", cmd, args)

        c = conn.cursor()
        c.execute(cmd, args)
        rows = [
            dict(row) for row in c.fetchall()
        ]  # Convert Row objects to dicts for JSON serialization
        for row in rows:
            try:
                row["age"] = github_style_duration(row["logtime"])
            except TypeError as e:
                logging.error("e=%s data=%s", e, row)

        return {
            "draw": draw,
            "recordsTotal": len(rows),
            "recordsFiltered": len(rows),  # Adjust if implementing search
            "data": rows,
        }

    def get_device_log(self, conn, device_id: int) -> Dict[str, Any]:
        """Get device log data"""

        c = conn.cursor()
        c.execute("""SELECT * from devices where device_id=?""", (device_id,))
        device = dict(c.fetchone())

        cmd = """SELECT *,datetime(logtime,'unixepoch','localtime') as start,
                             datetime(logtime+duration,'unixepoch','localtime') as end
                             from devlog where device_id=? """
        args = [device_id]
        (cmd, args) = temporal_quantification(cmd, args)

        cmd += " ORDER BY logtime DESC "

        c.execute(cmd, args)
        devlog = c.fetchall()

        cmd = "SELECT * from changelog where device_id=?"
        args = [device_id]
        (cmd, args) = temporal_quantification(cmd, args)

        cmd += " ORDER BY logtime DESC "

        c.execute(cmd, args)
        changelog = c.fetchall()

        return {
            "device": device,
            "devlog": devlog,
            "changelog": changelog
        }
