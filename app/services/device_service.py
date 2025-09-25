"""
Device-related business logic
"""
import logging
from typing import List, Dict, Any
from .. import ae200, db
from ..utils.time_utils import github_style_duration

logger = logging.getLogger(__name__)


class DeviceService:
    """Service for device-related operations"""

    def __init__(self):
        self.logger = logger

    def get_device_status(self, conn) -> List[Dict[str, Any]]:
        """Get device status with annotations"""
        device_data = db.fetch_last_status_fixed(conn)

        # Extract and convert the top-level drive, speed, and other items
        for data in device_data:
            if "status" in data:
                data.update(ae200.extract_drive_and_fan_speed(data["status"]))
            if "logtime" in data:
                data["age"] = github_style_duration(
                    data["logtime"] + data.get("duration", 1)
                )

        return device_data

    def get_temperature_series(self, conn, device_ids: List[int] = None) -> List[Dict[str, Any]]:
        """Get temperature series data for devices"""
        from ..utils.query_utils import temporal_quantification
        
        c = conn.cursor()
        series = []

        if device_ids:
            # Get specific devices
            for device_id in device_ids:
                c.execute("SELECT * from devices where device_id=?", (device_id,))
                device = c.fetchone()
                if device:
                    cmd = """
                        SELECT logtime,temp10x from devlog
                        where device_id=? and logtime is not null and temp10x is not null
                    """
                    args = [device_id]
                    (cmd, args) = temporal_quantification(cmd, args)
                    cmd += " order by logtime"

                    c.execute(cmd, args)
                    rows = c.fetchall()
                    data = [[row["logtime"], row["temp10x"] / 10] for row in rows]
                    if data:
                        series.append({"name": device["device_name"], "data": data})
        else:
            # Get all devices
            c.execute("SELECT * from devices")
            devices = c.fetchall()
            for dev in devices:
                cmd = """
                    SELECT logtime,temp10x from devlog
                    where device_id=? and logtime is not null and temp10x is not null
                """
                args = [dev["device_id"]]
                (cmd, args) = temporal_quantification(cmd, args)
                cmd += " order by logtime"

                c.execute(cmd, args)
                rows = c.fetchall()
                data = [[row["logtime"], row["temp10x"] / 10] for row in rows]
                if data:
                    series.append({"name": dev["device_name"], "data": data})

        return series
