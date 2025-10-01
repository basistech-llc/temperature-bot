"""
Web route handlers
"""
import logging
import datetime
import time
from flask import render_template, request
from ..services.device_service import DeviceService
from .common import LogService, with_db_connection, parse_device_ids, rules_engine, __version__

logger = logging.getLogger(__name__)

# Initialize services
device_service = DeviceService()
log_service = LogService()


def create_web_routes(app):
    """Create web routes and register them with the app"""

    @app.route("/")
    @with_db_connection
    def read_index(conn):
        """Main index page"""
        # Get device data for the template
        device_data = device_service.get_device_status(conn)

        # Add current timestamp for temporal links
        now = int(time.time())

        return render_template("index.html", develop=False, devices=device_data, now=now)

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
            rule_table.append("<tr><th>Time</th>" +
                              "".join([f"<th>AQI {aqi}</th>" for aqi in AQI_LIST]) +
                              "</tr>")
            for hour in range(24 * 7):
                when = hour_now + datetime.timedelta(hours=hour)
                rule_table.append(f"<tr><th>{str(when)}</th>")
                for aqi in AQI_LIST:
                    new_results = rules_engine.rules_results(conn, when.timestamp(), aqi=aqi)
                    rule_table.append(f"<td class='rule-result'>{new_results.replace('\n', '<br>')}</td>")
                rule_table.append("</tr>")

        disable_rules_until = rules_engine.disable_rules_until(conn)
        disable_rules_until_asc = time.asctime(time.localtime(disable_rules_until))
        return render_template(
            "rules.html",
            devices=rules_engine.get_devices_dict(conn),
            rules=rules_engine.get_rules(),
            rules_results="\n".join(rule_table),
            disable_rules_until=disable_rules_until,
            disable_rules_until_asc=disable_rules_until_asc,
            times=rules_engine.get_time_dict(),
        )

    @app.route("/logs")
    def do_logs():
        """Logs page"""
        return render_template("logs.html")

    @app.route("/device_log/<device_id>")
    @with_db_connection
    def device_log(conn, device_id):
        """Device log page"""
        log_data = log_service.get_device_log(conn, int(device_id))
        return render_template(
            "device_log.html",
            device=log_data["device"],
            devlog=log_data["devlog"],
            changelog=log_data["changelog"]
        )

    @app.route("/chart")
    def show_chart():
        """Chart page"""
        device_ids = parse_device_ids()

        return render_template("chart.html", device_ids=device_ids)

    @app.route("/privacy")
    def privacy():
        """Privacy page"""
        return render_template("privacy.html")

    @app.route("/buttons")
    def buttons():
        """Buttons page"""
        return render_template("buttons.html")

    @app.route("/version")
    def get_version():
        """Version page"""
        return f"version: {__version__}"
