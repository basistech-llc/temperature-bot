"""
Web route handlers
"""

import logging
import datetime
import time
import json
from flask import render_template, request

from .constants import __version__
from . import db
from . import rules_engine
from . import hubitat
from . import room_config
from .utils.request_utils import parse_device_ids
from .utils.db_utils import with_db_connection

logger = logging.getLogger(__name__)


def create_web_routes(app):
    """Create web routes and register them with the app"""

    @app.route("/")
    @with_db_connection
    def read_index(conn):
        """Main index page"""
        # Get device data for the template
        device_data = db.get_device_status(conn)

        # Add current timestamp for temporal links
        now = int(time.time())

        return render_template(
            "index.html",
            develop=False,
            devices=device_data,
            now=now,
            current_page="home",
        )

    @app.get("/health")
    def health():
        return {"status": "ok"}, 200

    @app.route("/rules")
    @with_db_connection
    def show_rules(conn):
        """Rules page"""
        # Check if we should run the rules or skip them
        run_rules = request.args.get("run_rules", "1", type=int)  # type: ignore
        hour_now = datetime.datetime.now().replace(minute=0, second=0, microsecond=0)

        # If requests, see how the rules will render for the next seven days
        rule_table = []
        AQI_LIST = [0, 51, 101, 151]
        if run_rules:
            rule_table.append("<table class='rules-table'>")
            rule_table.append(
                "<tr><th>Time</th>"
                + "".join([f"<th>AQI {aqi}</th>" for aqi in AQI_LIST])
                + "</tr>"
            )
            for hour in range(24 * 7):
                when = hour_now + datetime.timedelta(hours=hour)
                rule_table.append(f"<tr><th>{str(when)}</th>")
                for aqi in AQI_LIST:
                    new_results = rules_engine.rules_results(
                        conn, when.timestamp(), aqi=aqi
                    )
                    rule_table.append(
                        f"<td class='rule-result'>{new_results.replace('\n', '<br>')}</td>"
                    )
                rule_table.append("</tr>")

        rules_disabled_until = rules_engine.all_rules_disabled_until(conn)
        rules_disabled_until_asc = time.asctime(time.localtime(rules_disabled_until))
        return render_template(
            "rules.html",
            devices=db.devices_to_device_id(conn),
            times=rules_engine.get_time_dict(),
            air=rules_engine.get_air_dict(conn),
            rules=rules_engine.get_rules(),
            rules_results="\n".join(rule_table),
            rules_disabled_until=rules_disabled_until,
            rules_disabled_until_asc=rules_disabled_until_asc,
            current_page="rules",
        )

    @app.route("/logs")
    def do_logs():
        """Logs page"""
        return render_template("logs.html", current_page="logs")

    @app.route("/device_log/<device_id>")
    @with_db_connection
    def device_log(conn, device_id):
        """Device log page"""
        log_data = db.get_device_log(conn, int(device_id))
        alerts = db.get_alerts_for_device(conn, int(device_id))
        return render_template(
            "device_log.html",
            device=log_data["device"],
            devlog=log_data["devlog"],
            changelog=log_data["changelog"],
            alerts=alerts,
            current_page="logs",
        )

    @app.route("/chart")
    def show_chart():
        """Chart page"""
        device_ids = parse_device_ids()

        return render_template(
            "chart.html", device_ids=device_ids, current_page="chart"
        )

    @app.route("/alerts")
    @with_db_connection
    def show_alerts(conn):
        """Alerts page"""
        # Get devices as device_id:device_name for the dropdown
        c = conn.cursor()
        c.execute("SELECT device_id, device_name FROM devices ORDER BY device_name")
        devices = {dev["device_id"]: dev["device_name"] for dev in c.fetchall()}
        return render_template("alerts.html", devices=devices, current_page="alerts")

    @app.route("/privacy")
    def privacy():
        """Privacy page"""
        return render_template("privacy.html", current_page="privacy")

    @app.route("/terms")
    def terms():
        """Terms page"""
        return render_template("terms.html", current_page="terms")

    @app.route("/buttons")
    def buttons():
        """Buttons page"""
        return render_template("buttons.html", current_page="buttons")

    @app.route("/version")
    def get_version():
        """Version page"""
        return f"version: {__version__}"

    def _render_room_dashboard(location: str):
        """Helper function to render room dashboard"""
        return render_template(
            "room_dashboard.html",
            location=location,
            hide_nav=True,  # Hide navigation menu
        )

    @app.route("/dbg/all_devices")
    @with_db_connection
    def debug_all_devices(conn):
        """Debug endpoint to show all devices from database and Hubitat"""
        # Fetch all devices from database (like chart page shows)
        all_devices_names_json = None
        all_devices_json = None
        try:
            device_data = db.get_device_status(conn)
            # Extract just the names into a simple array
            device_names = [dev.get("device_name", "Unknown") for dev in device_data]
            all_devices_names_json = json.dumps(device_names, indent=2)
            # Format full data as JSON string for display
            all_devices_json = json.dumps(device_data, indent=2, default=str)
        except Exception as e:
            logger.warning("Failed to fetch all devices: %s", e)
            all_devices_names_json = json.dumps({"error": str(e)}, indent=2)
            all_devices_json = json.dumps({"error": str(e)}, indent=2)

        # Fetch Hubitat devices for testing
        hubitat_devices = None
        hubitat_names_json = None
        hubitat_json = None
        try:
            hubitat_devices = hubitat.get_all_devices()
            # Extract just the names into a simple array
            device_names = [dev.get("name", "Unknown") for dev in hubitat_devices]
            hubitat_names_json = json.dumps(device_names, indent=2)
            # Format full data as JSON string for display
            hubitat_json = json.dumps(hubitat_devices, indent=2)
        except Exception as e:
            logger.warning("Failed to fetch Hubitat devices: %s", e)
            hubitat_names_json = json.dumps({"error": str(e)}, indent=2)
            hubitat_json = json.dumps({"error": str(e)}, indent=2)

        return render_template(
            "debug_all_devices.html",
            all_devices_names_json=all_devices_names_json,
            all_devices_json=all_devices_json,
            hubitat_names_json=hubitat_names_json,
            hubitat_json=hubitat_json,
        )

    @app.route("/kitchen")
    @with_db_connection
    def kitchen_dashboard(conn):
        """Kitchen room dashboard"""
        return _render_room_dashboard_with_data(conn, "Kitchen")

    @app.route("/studio")
    @with_db_connection
    def studio_dashboard(conn):
        """Studio room dashboard"""
        return _render_room_dashboard_with_data(conn, "Studio")

    def _render_room_dashboard_with_data(conn, location: str):
        """Helper function to render room dashboard with device data"""
        # Get room config (location is "Kitchen" or "Studio", need lowercase key)
        room_key = location.lower()
        config = room_config.ROOM_CONFIGS.get(room_key, {})

        # Get all devices from database
        all_devices = db.get_device_status(conn)

        # Filter ERVs (devices with speed control matching ERV names)
        erv_devices = []
        for device in all_devices:
            if device.get("has_speed_control") and device.get(
                "device_name"
            ) in config.get("ervs", []):
                erv_devices.append(device)

        # Filter fans (devices with speed control matching fan names)
        # For studio, use first available fan from the list
        fan_devices = []
        fan_names = config.get("fans", [])
        if fan_names:
            for device in all_devices:
                if (
                    device.get("has_speed_control")
                    and device.get("device_name") in fan_names
                ):
                    fan_devices.append(device)
                    break  # Only take first match

        # Get Hubitat sensors
        # Filter by exact sensor name match
        hubitat_sensors = []
        try:
            all_hubitat = hubitat.get_all_devices()
            sensor_names = config.get("sensors", [])

            if sensor_names:
                # Filter by exact name match
                hubitat_sensors = [
                    dev
                    for dev in all_hubitat
                    if "TemperatureMeasurement" in dev.get("capabilities", [])
                    and dev.get("name") in sensor_names
                ]
            else:
                # If no sensors specified, show no sensors
                hubitat_sensors = []
        except Exception as e:
            logger.warning("Failed to fetch Hubitat sensors: %s", e)
            hubitat_sensors = []

        # Collect all notes from devices
        all_notes = []
        for device in erv_devices + fan_devices:
            notes = device.get("notes")
            if notes:
                all_notes.append(f"{device.get('device_name')}: {notes}")

        return render_template(
            "room_dashboard.html",
            location=location,
            hide_nav=True,
            config=config,
            erv_devices=erv_devices,
            fan_devices=fan_devices,
            hubitat_sensors=hubitat_sensors,
            notes=" | ".join(all_notes) if all_notes else None,
        )
