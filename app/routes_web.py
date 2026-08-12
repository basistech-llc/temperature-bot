"""Flask Web route handlers:

- Mostly just renders the appropriate template

- Note: We are slowly moving to server-side rendering
  ("pre-rendering") to make testing possible without using a chromium
  and a javascript interpreter.

"""

import logging
import datetime
import time
from flask import render_template, request, redirect, url_for
from markupsafe import escape

from .device_types import (
    DEVICE_TYPE_ERV,
    DEVICE_TYPE_FCU,
    DEVICE_TYPE_INTERNAL,
)
from .version import __version__
from . import db
from . import db_alerts
from . import rules_engine
from . import hubitat
from . import room_config
from .display_names import display_device_name
from .dashboard_views import build_dashboard_page
from .models import (
    DeviceMetadataControl,
    Room,
    RoomDashboardSensor,
    RoomDashboardSensorAttributes,
)
from .utils.request_utils import parse_device_ids
from .utils.db_utils import with_db_connection
from .routes_web_airquality_utils import (
    annotate_staleness,
    format_unix_as_asc,
)
from .room_metrics import RoomMetric, select_room_metric_sources
from .presence import PRESENCE_STALE_SECONDS, get_room_presence

logger = logging.getLogger(__name__)

# Display metadata for per-metric chart pages. Keyed on the URL-safe metric
# name (same keys as db.AQ_METRIC_STATUS_KEYS). Radon uses its default Bq/m³
# units here; metric_chart_support.js swaps to pCi/L when the user's site-wide
# temperature preference is Fahrenheit.
METRIC_CHART_CONFIG = {
    "humidity": {
        "label": "Humidity",
        "unit": "%",
        "decimals": 1,
        "y_axis_label": "Humidity (%)",
        "title": "Humidity Time Series",
    },
    "co2": {
        "label": "CO₂",
        "unit": "ppm",
        "decimals": 0,
        "y_axis_label": "CO₂ (ppm)",
        "title": "CO₂ Time Series",
    },
    "voc": {
        "label": "VOC",
        "unit": "ppb",
        "decimals": 0,
        "y_axis_label": "VOC (ppb)",
        "title": "VOC Time Series",
    },
    "radon": {
        "label": "Radon",
        "unit": "Bq/m³",
        "decimals": 0,
        "y_axis_label": "Radon (Bq/m³)",
        "title": "Radon Time Series",
    },
    "pm25": {
        "label": "PM2.5",
        "unit": "µg/m³",
        "decimals": 1,
        "y_axis_label": "PM2.5 (µg/m³)",
        "title": "PM2.5 Time Series",
    },
    "pm1": {
        "label": "PM1",
        "unit": "µg/m³",
        "decimals": 1,
        "y_axis_label": "PM1 (µg/m³)",
        "title": "PM1 Time Series",
    },
    "pressure": {
        "label": "Pressure",
        "unit": "hPa",
        "decimals": 1,
        "y_axis_label": "Pressure (hPa)",
        "title": "Pressure Time Series",
    },
}


def _rules_forecast_table(conn, hour_now: datetime.datetime) -> list[str]:
    """Build the seven-day forecast with one compiled rules program."""
    aqi_values = (0, 51, 101, 151)
    compiled_rules = rules_engine.compile_rules()
    rows = [
        "<table class='rules-table'>",
        "<tr><th>Time</th>"
        + "".join(f"<th>AQI {aqi}</th>" for aqi in aqi_values)
        + "</tr>",
    ]
    for hour in range(24 * 7):
        when = hour_now + datetime.timedelta(hours=hour)
        rows.append(f"<tr><th>{when}</th>")
        for aqi in aqi_values:
            results = rules_engine.rules_results(
                conn,
                when.timestamp(),
                aqi=aqi,
                compiled_rules=compiled_rules,
            )
            formatted_results = _format_rules_result(results)
            rows.append(f"<td class='rule-result'>{formatted_results}</td>")
        rows.append("</tr>")
    rows.append("</table>")
    return rows


def _format_rules_result(result: str) -> str:
    """Escape dynamic rule output while preserving visible line breaks."""
    return str(escape(result)).replace("\n", "<br>")


def _register_core_routes(app):
    """Register core web routes that back the main navigation."""

    @app.route("/")
    @with_db_connection
    def read_index(conn):
        """Main index page"""
        page = build_dashboard_page(
            db.get_device_status(conn),
            db.get_rooms(conn),
            db.get_assigned_room_ids(conn),
        )
        return render_template(
            "index.html",
            develop=False,
            devices=page.devices,
            now=page.now,
            table_update_summaries=page.table_update_summaries,
            room_groups=page.room_groups,
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
        try:
            run_rules = int(request.args.get("run_rules", "1"))
        except ValueError:
            run_rules = 1
        hour_now = datetime.datetime.now().replace(minute=0, second=0, microsecond=0)

        # If requests, see how the rules will render for the next seven days
        rule_table = _rules_forecast_table(conn, hour_now) if run_rules else []

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
        """Activity Log page"""
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
            "temperature_chart.html",
            device_ids=device_ids,
            current_page="temperature_chart",
        )

    @app.get("/fcu_chart")
    def show_fcu_chart():
        """Combined FCU inlet, calculated room, and operating-state chart."""
        return render_template(
            "fcu_history_chart.html",
            fcu_device_id=request.args.get("fcu_device_id", type=int),
            current_page="temperature_chart",
        )

    @app.route("/lighting_chart")
    def show_lighting_chart():
        """Lighting (illuminance) chart page"""
        return render_template(
            "lighting_chart.html", current_page="lighting_chart"
        )

    @app.route("/metric_chart")
    def show_metric_chart():
        """Time-series chart for a single air-quality metric across devices."""
        metric = request.args.get("metric", "")
        if metric not in db.AQ_METRIC_STATUS_KEYS:
            return (
                f"Unknown metric: {metric!r}. "
                f"Expected one of: {sorted(db.AQ_METRIC_STATUS_KEYS)}",
                400,
            )
        metric_config = METRIC_CHART_CONFIG[metric]
        return render_template(
            "metric_chart.html",
            current_page="metric_chart",
            metric=metric,
            metric_config=metric_config,
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

        # Attach a centralized display name for each row so templates do not
        # need to know about vendor prefixes, " on " suffixes, etc.
        for row in airmon:
            raw_name = row.get("device_name", "")
            row["display_name"] = display_device_name(raw_name, source="airthings")

        annotate_staleness(airmon)

        # Indoor data timestamp: newest devlog logtime among indoor devices
        indoor_ts = None
        for row in airmon:
            status = row.get("status") or {}
            if "aqi" in status:
                continue
            if "logtime" in row:
                if indoor_ts is None or row["logtime"] > indoor_ts:
                    indoor_ts = row["logtime"]

        indoor_asof = format_unix_as_asc(indoor_ts)

        # Outdoor AQI timestamp: latest logtime from aqi table
        c = conn.cursor()
        c.execute("SELECT logtime FROM aqi ORDER BY logtime DESC LIMIT 1")
        row = c.fetchone()
        outdoor_asof = format_unix_as_asc(row[0] if row is not None else None)

        return render_template(
            "air-quality.html",
            current_page="air-quality",
            airmon=airmon,
            indoor_asof=indoor_asof,
            outdoor_asof=outdoor_asof,
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

    return app


def _filter_speed_control_devices(devices, device_names):
    """Filter devices with speed control matching given names."""
    return [
        device
        for device in devices
        if device.get("has_speed_control")
        and device.get("device_name") in device_names
    ]


def _get_hubitat_sensors(sensor_names):
    """Fetch and filter Hubitat temperature sensors by exact name match.

    Returns an entry for every configured name.  Sensors not found in
    Hubitat (or unreachable) are represented as placeholder dicts with
    ``offline=True`` so the template can still render them.
    """
    if not sensor_names:
        return []

    try:
        all_hubitat = hubitat.get_all_devices()
    except (ValueError, RuntimeError, OSError) as e:
        logger.warning("Failed to fetch Hubitat sensors: %s", e)
        all_hubitat = []

    found = [
        dev
        for dev in all_hubitat
        if "TemperatureMeasurement" in dev.get("capabilities", [])
        and dev.get("name") in sensor_names
    ]
    found_names = {dev.get("name") for dev in found}

    for name in sensor_names:
        if name not in found_names:
            logger.warning("Configured sensor %r not found in Hubitat", name)
            found.append({"name": name, "label": name, "offline": True, "attributes": {}})

    return found


def _canonical_room_sensors(conn, room_id: int) -> list[RoomDashboardSensor]:
    """Build room sensor tiles from persisted assignment and shared freshness."""
    snapshots = db.fetch_latest_room_metric_snapshots(conn)
    at_time = time.time()
    temperatures = select_room_metric_sources(
        snapshots, room_id=room_id, metric=RoomMetric.TEMPERATURE, at_time=at_time
    )
    humidities = select_room_metric_sources(
        snapshots, room_id=room_id, metric=RoomMetric.HUMIDITY, at_time=at_time
    )
    temperature_by_device = {
        source.device_id: source.value for source in temperatures.sources
    }
    humidity_by_device = {
        source.device_id: source.value for source in humidities.sources
    }
    return sorted(
        [
            RoomDashboardSensor(
                id=snapshot.device_id,
                name=snapshot.device_name,
                display_name=snapshot.display_name or snapshot.device_name,
                offline=snapshot.device_id not in temperature_by_device,
                attributes=RoomDashboardSensorAttributes(
                    temperature=temperature_by_device.get(snapshot.device_id),
                    humidity=(
                        round(humidity_by_device[snapshot.device_id])
                        if snapshot.device_id in humidity_by_device
                        else None
                    ),
                ),
            )
            for snapshot in snapshots
            if snapshot.room_id == room_id
            and snapshot.device_type
            not in {DEVICE_TYPE_FCU, DEVICE_TYPE_ERV, DEVICE_TYPE_INTERNAL}
            and snapshot.temp10x is not None
        ],
        key=lambda sensor: (sensor.display_name.casefold(), sensor.id),
    )


def _collect_device_notes(devices):
    """Collect notes from devices and format as banner text."""
    notes = [
        f"{device.get('device_name')}: {device.get('notes')}"
        for device in devices
        if device.get("notes")
    ]
    return " | ".join(notes) if notes else None


def _room_control_key(conn, room: Room | None, fallback: str) -> str:
    """Bind configured controls to the room's stable owning FCU identity."""
    if room and room.fcu_device_id:
        owner = db.get_device(conn, room.fcu_device_id)
        owner_key = str((owner or {}).get("device_name") or "").casefold()
        if room_config.find_room_config(owner_key) is not None:
            return owner_key
    return fallback.casefold()


def _render_room_dashboard_with_data(conn, location: str, room_id: int | None = None):
    """Render room dashboard with device data filtered by configuration."""
    room_key = location.lower()
    rooms = db.get_rooms(conn)
    room = db.get_room(conn, room_id) if room_id is not None else next(
        (
            candidate
            for candidate in rooms
            if (candidate.room_name or "").casefold() == room_key
        ),
        None,
    )
    if room is None and room_id is None:
        room = next(
            (
                candidate
                for candidate in rooms
                if _room_control_key(conn, candidate, "") == room_key
            ),
            None,
        )
    if room_id is not None and room is None:
        return "Unknown room", 404
    control_key = _room_control_key(conn, room, room_key)
    config = room_config.get_room_config(control_key)

    all_devices = db.get_device_status(conn)

    # Filter ERVs and fans
    erv_devices = _filter_speed_control_devices(all_devices, config.ervs)

    fan_devices = _filter_speed_control_devices(all_devices, config.fans)

    hubitat_sensors = (
        _canonical_room_sensors(conn, room.room_id)
        if room and room.room_id
        else []
    )

    # Collect notes
    notes = _collect_device_notes(erv_devices + fan_devices)

    embedded = "embedded" in request.args

    return render_template(
        "room_dashboard.html",
        location=room.room_name if room and room.room_name else location,
        hide_nav=True,
        embedded=embedded,
        erv_devices=erv_devices,
        fan_devices=fan_devices,
        hubitat_sensors=hubitat_sensors,
        notes=notes,
        show_tv_control=config.tv_control,
        dimmer_id=config.dimmer_id,
        wall_inner_id=config.wall_inner_id,
        wall_outer_id=config.wall_outer_id,
        room_control_key=control_key,
    )


def _register_room_routes(app):
    """Register routes related to room dashboards and debug views."""

    @app.route("/all_devices")
    def debug_all_devices():
        """Debug endpoint to show all devices from database and Hubitat"""
        # Render page immediately, data will be loaded asynchronously
        return render_template(
            "debug_all_devices.html",
            current_page="all_devices",
        )

    @app.route("/devices", methods=["GET", "POST"])
    @with_db_connection
    def edit_devices(conn):
        """Edit device metadata."""
        if request.method == "POST":
            for raw_device_id in request.form.getlist("device_id"):
                body = DeviceMetadataControl(
                    device_id=int(raw_device_id),
                    display_name=request.form.get(f"display_name_{raw_device_id}"),
                    rules_enabled=f"rules_enabled_{raw_device_id}" in request.form,
                    notes=request.form.get(f"notes_{raw_device_id}"),
                )
                db.update_device_metadata(
                    conn,
                    body,
                    fields={"display_name", "rules_enabled", "notes"},
                )
            return redirect(url_for("edit_devices"))
        return render_template(
            "devices.html",
            devices=db.get_device_metadata(conn),
            current_page="devices",
        )

    @app.get("/map")
    def room_map():
        """Render the canonical room-backed HVAC floor-plan overlay."""
        return render_template("map.html", current_page="map")

    @app.get("/presence")
    @with_db_connection
    def presence_table(conn):
        """Render room presence with explicit unknown and stale states."""
        return render_template(
            "presence.html",
            current_page="presence",
            rooms=get_room_presence(conn),
            stale_minutes=PRESENCE_STALE_SECONDS // 60,
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

    @app.get("/room/<int:room_id>")
    @with_db_connection
    def canonical_room_dashboard(conn, room_id: int):
        """Render a stable-id room dashboard whose name may change."""
        room = db.get_room(conn, room_id)
        if room is None:
            return "Unknown room", 404
        return _render_room_dashboard_with_data(
            conn, room.room_name or "Room", room_id=room_id
        )

    return app


def create_web_routes(app):
    """Create web routes and register them with the app."""
    _register_core_routes(app)
    _register_room_routes(app)
    return app
