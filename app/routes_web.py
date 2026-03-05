"""Flask Web route handlers:

- Mostly just renders the appropriate template

- Note: We are slowly moving to server-side rendering
  ("pre-rendering") to make testing possible without using a chromium
  and a javascript interpreter.

"""

import logging
import datetime
import time
from typing import List
from flask import render_template, request, redirect, url_for

from .constants import __version__
from . import db
from . import db_alerts
from . import rules_engine
from . import hubitat
from . import room_config
from .utils.request_utils import parse_device_ids
from .utils.db_utils import with_db_connection

logger = logging.getLogger(__name__)


def create_web_routes(app):
    """Create web routes and register them with the app"""

    def _score_metric(metric_name, value):
        """Return (severity_score, label, short_name) for a metric value.

        severity_score: 0=good, 1=elevated, 2=problem
        """
        if value is None:
            return (0, "good", metric_name)

        # Defaults
        score = 0
        label = "good"
        short_name = metric_name

        if metric_name == "co2":
            short_name = "CO₂"
            if value > 1200:
                score, label = 2, "problem"
            elif value > 800:
                score, label = 1, "elevated"
        elif metric_name == "pm25":
            short_name = "PM2.5"
            if value > 35:
                score, label = 2, "problem"
            elif value > 12:
                score, label = 1, "elevated"
        elif metric_name == "pm1":
            short_name = "PM1"
            if value > 35:
                score, label = 2, "problem"
            elif value > 12:
                score, label = 1, "elevated"
        elif metric_name == "humidity":
            short_name = "RH"
            if value < 30 or value > 60:
                score, label = 2, "problem"
            elif value < 35 or value > 55:
                score, label = 1, "elevated"
        elif metric_name == "temp":
            short_name = "Temp"
            if value < 18 or value > 27:
                score, label = 2, "problem"
            elif value < 20 or value > 25:
                score, label = 1, "elevated"
        elif metric_name == "radonShortTermAvg":
            short_name = "Radon"
            # Thresholds chosen as a reasonable default; adjust to local units if needed.
            if value > 150:
                score, label = 2, "problem"
            elif value > 100:
                score, label = 1, "elevated"
        elif metric_name == "voc":
            short_name = "VOC"
            if value > 2000:
                score, label = 2, "problem"
            elif value > 500:
                score, label = 1, "elevated"

        return (score, label, short_name)

    def _compute_indoor_air_summary(airmon):
        """Summarize indoor air issues across multiple metrics."""
        issues = []

        for row in airmon:
            status = row.get("status") or {}
            # Skip synthetic outdoor AQI row, which only has status["aqi"]
            if "aqi" in status:
                continue

            device_name = row.get("device_name", "")
            for metric_name in [
                "co2",
                "pm25",
                "pm1",
                "humidity",
                "temp",
                "radonShortTermAvg",
                "voc",
            ]:
                val_dict = status.get(metric_name)
                value = None
                if isinstance(val_dict, dict):
                    value = val_dict.get("value")
                elif isinstance(val_dict, (int, float)):
                    value = val_dict

                score, label, short_name = _score_metric(metric_name, value)
                if score > 0 and value is not None:
                    issues.append(
                        {
                            "device_name": device_name,
                            "metric": short_name,
                            "value": value,
                            "score": score,
                            "label": label,
                        }
                    )

        if not issues:
            return {
                "state": "clear",
                "issues": [],
            }

        # Determine overall state
        worst_score = max(i["score"] for i in issues)
        if worst_score >= 2:
            state = "alert"
        else:
            state = "watch"

        # Sort issues: highest score first, then by value descending, and keep top 3
        issues_sorted = sorted(
            issues, key=lambda i: (i["score"], i["value"]), reverse=True
        )[:3]

        return {
            "state": state,
            "issues": [
                {
                    "device_name": i["device_name"],
                    "metric": i["metric"],
                    "value": i["value"],
                }
                for i in issues_sorted
            ],
        }

    @app.route("/")
    @with_db_connection
    def read_index(conn):
        """Main index page"""
        # Get device data for the template
        device_data = db.get_device_status(conn)

        # Enrich with Hubitat label for display (Air Quality section: label visible, name in title)
        name_to_label = hubitat.get_name_to_label()
        for d in device_data:
            d["device_label"] = name_to_label.get(d["device_name"], d["device_name"])

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

    @app.route("/logs_today")
    def logs_today():
        """Today's Log page"""
        return render_template("logs_today.html", current_page="logs_today")

    @app.route("/device_log/<device_id>")
    @with_db_connection
    def device_log(conn, device_id):
        """Device log page"""
        log_data = db.get_device_log(conn, int(device_id))
        alerts = db_alerts.get_alerts_for_device(conn, int(device_id))
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
        """Temperature chart page"""
        device_ids = parse_device_ids()

        return render_template(
            "chart.html", device_ids=device_ids, current_page="chart"
        )

    @app.route("/chart_aqi")
    def show_chart_aqi():
        """Air Quality chart page"""
        return render_template(
            "chart_aqi.html", current_page="chart_aqi"
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

    @app.route("/air-quality")
    @with_db_connection
    def air_quality(conn):
        """Real-time Air Quality page"""
        airmon = db.get_all_device_aqi(conn)
        indoor_summary = _compute_indoor_air_summary(airmon)
        return render_template(
            "air-quality.html",
            current_page="air-quality",
            airmon=airmon,
            indoor_summary=indoor_summary,
        )

    @app.route("/weather")
    def weather():
        """Weather page"""
        return render_template("weather.html", current_page="weather")

    @app.route("/about")
    def about():
        """About page"""
        return render_template("about.html", current_page="about")

    @app.route("/privacy")
    def privacy():
        """Privacy page - redirects to About"""
        return redirect(url_for("about"))

    @app.route("/terms")
    def terms():
        """Terms page - redirects to About"""
        return redirect(url_for("about"))

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

    @app.route("/all_devices")
    def debug_all_devices():
        """Debug endpoint to show all devices from database and Hubitat"""
        # Render page immediately, data will be loaded asynchronously
        return render_template(
            "debug_all_devices.html",
            current_page="all_devices",
        )

    @app.route("/kitchen")
    @with_db_connection
    def kitchen_dashboard(conn):
        """Kitchen HVAC control dashboard."""
        return _render_room_dashboard_with_data(conn, "Kitchen")

    @app.route("/hickory")
    @with_db_connection
    def hickory_dashboard(conn):
        """Hickory HVAC control dashboard."""
        return _render_room_dashboard_with_data(conn, "Hickory")

    def _filter_speed_control_devices(devices, device_names):
        """Filter devices with speed control matching given names."""
        return [
            device
            for device in devices
            if device.get("has_speed_control")
            and device.get("device_name") in device_names
        ]

    def _get_hubitat_sensors(sensor_names):
        """Fetch and filter Hubitat temperature sensors by exact name match."""
        if not sensor_names:
            return []

        try:
            all_hubitat = hubitat.get_all_devices()
            return [
                dev
                for dev in all_hubitat
                if "TemperatureMeasurement" in dev.get("capabilities", [])
                and dev.get("name") in sensor_names
            ]
        except (ValueError, RuntimeError, OSError) as e:
            logger.warning("Failed to fetch Hubitat sensors: %s", e)
            return []

    def _collect_device_notes(devices):
        """Collect notes from devices and format as banner text."""
        notes = [
            f"{device.get('device_name')}: {device.get('notes')}"
            for device in devices
            if device.get("notes")
        ]
        return " | ".join(notes) if notes else None

    def _render_room_dashboard_with_data(conn, location: str):
        """Render room dashboard with device data filtered by configuration."""
        room_key = location.lower()
        config = room_config.ROOM_CONFIGS.get(room_key, {})

        all_devices = db.get_device_status(conn)

        # Filter ERVs and fans
        erv_devices = _filter_speed_control_devices(all_devices, config.get("ervs", []))

        # For fans, take first available match
        fan_names: List[str] = config.get("fans", [])
        fan_devices = []
        if fan_names:
            filtered = _filter_speed_control_devices(all_devices, fan_names)
            if filtered:
                fan_devices = [filtered[0]]  # Only first match

        # Get Hubitat sensors
        hubitat_sensors = _get_hubitat_sensors(config.get("sensors", []))

        # Collect notes
        notes = _collect_device_notes(erv_devices + fan_devices)

        return render_template(
            "room_dashboard.html",
            location=location,
            hide_nav=True,
            erv_devices=erv_devices,
            fan_devices=fan_devices,
            hubitat_sensors=hubitat_sensors,
            notes=notes,
        )
