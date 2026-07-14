#!/usr/bin/env python3
"""Render the Flask web UI pages to PNG screenshots.

The program seeds a temporary SQLite database, starts the Flask app against
that database, drives Chromium with Playwright, and writes one PNG per
user-facing web page plus a manifest and Markdown gallery.
"""

from __future__ import annotations

import argparse
import copy
import datetime as dt
import json
import os
import socket
import sqlite3
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

import requests
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright
from pydantic import BaseModel, Field

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))
DEFAULT_OUTPUT_DIR = ROOT_DIR / "var" / "web-ui-screenshots"
DEFAULT_CONFIG = ROOT_DIR / "tests" / "temperature-bot-config-test.yaml"
DEFAULT_VIEWPORT_WIDTH = 1440
DEFAULT_VIEWPORT_HEIGHT = 1200
DEFAULT_TIMEOUT_MS = 20_000

DRIVE_KEY = "Drive"
FAN_SPEED_KEY = "FanSpeed"
INLET_TEMP_KEY = "InletTemp"
SET_TEMP_KEY = "SetTemp"
MODE_KEY = "Mode"
FILTER_SIGN_KEY = "FilterSign"
CHECK_WATER_KEY = "CheckWater"
ERROR_SIGN_KEY = "ErrorSign"
ILLUMINANCE_KEY = "illuminance"
ATTRIBUTES_KEY = "attributes"
TEMPERATURE_KEY = "temperature"
TEMP_KEY = "temp"
HUMIDITY_KEY = "humidity"
CO2_KEY = "co2"
VOC_KEY = "voc"
RADON_KEY = "radonShortTermAvg"
PM25_KEY = "pm25"
PM1_KEY = "pm1"
PRESSURE_KEY = "pressure"
VALUE_KEY = "value"
UNIT_KEY = "unit"

HUBITAT_ID_KEY = "id"
HUBITAT_NAME_KEY = "name"
HUBITAT_LABEL_KEY = "label"
HUBITAT_CAPABILITIES_KEY = "capabilities"
HUBITAT_ATTRIBUTES_KEY = "attributes"


class PageSpec(BaseModel):
    """One user-facing page to render."""

    slug: str
    title: str
    path: str
    wait_selector: str | None = None
    wait_text_selector: str | None = None
    wait_text: str | None = None
    settle_ms: int = Field(default=700, ge=0)


class RenderedPage(BaseModel):
    """Manifest entry for one rendered page."""

    slug: str
    title: str
    path: str
    url: str
    filename: str
    status: int
    console_errors: list[str] = Field(default_factory=list)
    page_errors: list[str] = Field(default_factory=list)


class RenderManifest(BaseModel):
    """Screenshot run manifest."""

    generated_at: str
    base_url: str
    viewport_width: int
    viewport_height: int
    pages: list[RenderedPage]


class SeedDevice(BaseModel):
    """Synthetic device inserted into the screenshot database."""

    name: str
    temp_c: float
    status: dict[str, Any]
    ae200_device_id: int | None = None
    notes: str | None = None
    aqi_mon: bool = False


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Render all web UI pages to PNG screenshots."
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory for PNGs, manifest.json, and gallery.md.",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=0, help="0 chooses a free port.")
    parser.add_argument("--width", type=int, default=DEFAULT_VIEWPORT_WIDTH)
    parser.add_argument("--height", type=int, default=DEFAULT_VIEWPORT_HEIGHT)
    parser.add_argument("--timeout-ms", type=int, default=DEFAULT_TIMEOUT_MS)
    return parser.parse_args()


def metric(value: float, unit: str) -> dict[str, Any]:
    return {VALUE_KEY: value, UNIT_KEY: unit}


def ae200_status(
    *,
    drive: str,
    fan_speed: str,
    inlet_temp: float,
    set_temp: float,
    illuminance: int | None = None,
) -> dict[str, Any]:
    status: dict[str, Any] = {
        DRIVE_KEY: drive,
        FAN_SPEED_KEY: fan_speed,
        INLET_TEMP_KEY: f"{inlet_temp:.1f}",
        SET_TEMP_KEY: f"{set_temp:.1f}",
        MODE_KEY: "AUTO",
        FILTER_SIGN_KEY: "OFF",
        CHECK_WATER_KEY: "OFF",
        ERROR_SIGN_KEY: "OFF",
    }
    if illuminance is not None:
        status[ILLUMINANCE_KEY] = illuminance
    return status


def airthings_status(
    *,
    temp_c: float,
    humidity: float,
    co2: float,
    voc: float,
    radon: float,
    pm25: float,
    pm1: float,
    pressure: float,
) -> dict[str, Any]:
    return {
        TEMP_KEY: metric(temp_c, "degC"),
        TEMPERATURE_KEY: metric(temp_c, "degC"),
        HUMIDITY_KEY: metric(humidity, "%"),
        CO2_KEY: metric(co2, "ppm"),
        VOC_KEY: metric(voc, "ppb"),
        RADON_KEY: metric(radon, "Bq/m3"),
        PM25_KEY: metric(pm25, "ug/m3"),
        PM1_KEY: metric(pm1, "ug/m3"),
        PRESSURE_KEY: metric(pressure, "hPa"),
    }


def hubitat_status(*, temp_c: float, humidity: float, illuminance: int) -> dict[str, Any]:
    return {
        ATTRIBUTES_KEY: {
            TEMPERATURE_KEY: temp_c,
            HUMIDITY_KEY: humidity,
            ILLUMINANCE_KEY: illuminance,
        },
        TEMPERATURE_KEY: temp_c,
        HUMIDITY_KEY: humidity,
        ILLUMINANCE_KEY: illuminance,
    }


def seed_devices() -> list[SeedDevice]:
    return [
        SeedDevice(
            name="ERV Kitchen",
            ae200_device_id=10,
            temp_c=21.7,
            status=ae200_status(
                drive="ON",
                fan_speed="MID1",
                inlet_temp=21.7,
                set_temp=21.0,
                illuminance=310,
            ),
            notes="Kitchen ERV is in normal service.",
        ),
        SeedDevice(
            name="Kitchen",
            ae200_device_id=11,
            temp_c=22.4,
            status=ae200_status(
                drive="ON",
                fan_speed="AUTO",
                inlet_temp=22.4,
                set_temp=22.0,
                illuminance=420,
            ),
        ),
        SeedDevice(
            name="ERV Restrooms",
            ae200_device_id=12,
            temp_c=20.9,
            status=ae200_status(
                drive="ON",
                fan_speed="HIGH",
                inlet_temp=20.9,
                set_temp=21.0,
                illuminance=180,
            ),
        ),
        SeedDevice(
            name="Restrooms/BOH",
            ae200_device_id=13,
            temp_c=21.2,
            status=ae200_status(
                drive="OFF",
                fan_speed="MID2",
                inlet_temp=21.2,
                set_temp=21.5,
                illuminance=120,
            ),
            notes="Recently serviced.",
        ),
        SeedDevice(
            name="Dungeon",
            ae200_device_id=14,
            temp_c=19.8,
            status=ae200_status(
                drive="ON",
                fan_speed="MID2",
                inlet_temp=19.8,
                set_temp=20.0,
                illuminance=60,
            ),
        ),
        SeedDevice(
            name="Airthings Kitchen",
            temp_c=22.1,
            status=airthings_status(
                temp_c=22.1,
                humidity=43.0,
                co2=690,
                voc=140,
                radon=28,
                pm25=4.1,
                pm1=2.7,
                pressure=1011.2,
            ),
            aqi_mon=True,
        ),
        SeedDevice(
            name="Airthings Hickory",
            temp_c=20.6,
            status=airthings_status(
                temp_c=20.6,
                humidity=49.0,
                co2=840,
                voc=220,
                radon=44,
                pm25=7.3,
                pm1=3.9,
                pressure=1012.4,
            ),
            aqi_mon=True,
        ),
        SeedDevice(
            name="Lobby Sensor on Somerville Broadway",
            temp_c=21.9,
            status=hubitat_status(temp_c=21.9, humidity=45.0, illuminance=510),
        ),
        SeedDevice(
            name="Broadway Sensor Center on Somerville Broadway",
            temp_c=22.0,
            status=hubitat_status(temp_c=22.0, humidity=44.0, illuminance=480),
        ),
        SeedDevice(
            name="Broadway Sensor North on Somerville Broadway",
            temp_c=21.3,
            status=hubitat_status(temp_c=21.3, humidity=46.0, illuminance=455),
        ),
        SeedDevice(
            name="Broadway Sensor South on Somerville Broadway",
            temp_c=21.5,
            status=hubitat_status(temp_c=21.5, humidity=47.0, illuminance=465),
        ),
        SeedDevice(
            name="Hickory Sensor",
            temp_c=20.4,
            status=hubitat_status(temp_c=20.4, humidity=48.0, illuminance=260),
        ),
        SeedDevice(
            name="Dungeon Cage",
            temp_c=19.6,
            status=hubitat_status(temp_c=19.6, humidity=52.0, illuminance=80),
        ),
    ]


def fake_hubitat_devices() -> list[dict[str, Any]]:
    sensor_devices = []
    for device in seed_devices():
        attrs = device.status.get(ATTRIBUTES_KEY)
        if not isinstance(attrs, dict):
            continue
        sensor_devices.append(
            {
                HUBITAT_ID_KEY: str(1000 + len(sensor_devices)),
                HUBITAT_NAME_KEY: device.name,
                HUBITAT_LABEL_KEY: device.name.replace(" on Somerville Broadway", ""),
                HUBITAT_CAPABILITIES_KEY: ["TemperatureMeasurement"],
                HUBITAT_ATTRIBUTES_KEY: attrs,
                "room": "Screenshot",
                "type": "Generic Component Temperature Sensor",
            }
        )
    sensor_devices.extend(
        [
            {
                HUBITAT_ID_KEY: "581",
                HUBITAT_NAME_KEY: "Hickory Main Lights",
                HUBITAT_LABEL_KEY: "Main Lights",
                HUBITAT_CAPABILITIES_KEY: ["SwitchLevel"],
                HUBITAT_ATTRIBUTES_KEY: {"level": 62, "switch": "on"},
            },
            {
                HUBITAT_ID_KEY: "454",
                HUBITAT_NAME_KEY: "Green Wall Inner",
                HUBITAT_LABEL_KEY: "Green Wall Inner",
                HUBITAT_CAPABILITIES_KEY: ["Switch"],
                HUBITAT_ATTRIBUTES_KEY: {"switch": "on"},
            },
            {
                HUBITAT_ID_KEY: "550",
                HUBITAT_NAME_KEY: "Green Wall Outer",
                HUBITAT_LABEL_KEY: "Green Wall Outer",
                HUBITAT_CAPABILITIES_KEY: ["Switch"],
                HUBITAT_ATTRIBUTES_KEY: {"switch": "off"},
            },
        ]
    )
    return sensor_devices


def fake_weather_data() -> dict[str, Any]:
    return {
        "stations": [
            {
                "station_name": "Boston Logan",
                "temperature": 23.0,
                "conditions": "Mostly Sunny",
                "icon": "",
            },
            {
                "station_name": "Norwood Memorial",
                "temperature": 24.4,
                "conditions": "Clear",
                "icon": "",
            },
        ],
        "forecast": [
            {"time": "12:00", "temperature": 74, "conditions": "Sunny", "icon": ""},
            {"time": "13:00", "temperature": 76, "conditions": "Sunny", "icon": ""},
            {"time": "14:00", "temperature": 78, "conditions": "Partly Cloudy", "icon": ""},
            {"time": "15:00", "temperature": 77, "conditions": "Partly Cloudy", "icon": ""},
            {"time": "16:00", "temperature": 75, "conditions": "Breezy", "icon": ""},
        ],
        "daily": [
            {"name": "Today", "temperature": 78, "conditions": "Sunny"},
            {"name": "Tonight", "temperature": 61, "conditions": "Mostly Clear"},
            {"name": "Tomorrow", "temperature": 81, "conditions": "Warm"},
            {"name": "Tomorrow Night", "temperature": 64, "conditions": "Clear"},
            {"name": "Tuesday", "temperature": 79, "conditions": "Clouds Increasing"},
        ],
    }


def configure_environment(db_path: Path) -> None:
    os.environ["DB_PATH"] = str(db_path)
    os.environ["TEST_DB_NAME"] = str(db_path)
    os.environ["PYTEST"] = "1"
    os.environ.setdefault("AE200_SIMULATOR", "1")
    os.environ.setdefault("AIRTHINGS_SIMULATOR", "1")
    os.environ.setdefault("AQICN_SIMULATOR", "1")
    os.environ.setdefault("TEMPERATURE_BOT_CONFIG", str(DEFAULT_CONFIG))
    os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(ROOT_DIR / ".playwright"))


def prepare_output_dir(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for path in output_dir.glob("*.png"):
        path.unlink()
    for name in ("manifest.json", "gallery.md"):
        target = output_dir / name
        if target.exists():
            target.unlink()


def create_database(db_path: Path) -> dict[str, int]:
    from app.paths import SCHEMA_FILE_PATH

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        conn.executescript(Path(SCHEMA_FILE_PATH).read_text(encoding="utf-8"))
        now = int(time.time())
        device_ids: dict[str, int] = {}
        for device in seed_devices():
            device_type = (
                "ERV"
                if device.name.startswith("ERV ")
                else "FCU"
                if device.ae200_device_id is not None
                else "SENSOR"
            )
            cursor = conn.execute(
                """
                INSERT INTO devices
                    (device_name, device_type, ae200_device_id, disabled_until, notes, aqi_mon)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    device.name,
                    device_type,
                    device.ae200_device_id,
                    0,
                    device.notes,
                    1 if device.aqi_mon else 0,
                ),
            )
            device_id = int(cursor.lastrowid)
            device_ids[device.name] = device_id
            for index, seconds_ago in enumerate((3600, 6 * 3600, 26 * 3600, 4 * 86400)):
                status = varied_status(device.status, index)
                temp_c = device.temp_c + (index - 1.5) * 0.3
                conn.execute(
                    """
                    INSERT INTO devlog
                        (device_id, logtime, duration, temp10x, status_json)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        device_id,
                        now - seconds_ago,
                        1800,
                        int(round(temp_c * 10)),
                        json.dumps(status, sort_keys=True),
                    ),
                )

        room_ids: dict[str, int] = {}
        for room_name, fcu_name in (
            ("Atrium", None),
            ("Dungeon", "Dungeon"),
            ("Hickory", None),
            ("Kitchen", "Kitchen"),
            ("Restrooms/BOH", "Restrooms/BOH"),
        ):
            cursor = conn.execute(
                "INSERT INTO rooms (room_name, fcu_device_id) VALUES (?, ?)",
                (room_name, device_ids.get(fcu_name) if fcu_name else None),
            )
            room_ids[room_name] = int(cursor.lastrowid)
            if fcu_name:
                conn.execute(
                    "UPDATE devices SET room_id=? WHERE device_id=?",
                    (room_ids[room_name], device_ids[fcu_name]),
                )
        for device_name, room_name in (
            ("Airthings Kitchen", "Kitchen"),
            ("Airthings Hickory", "Hickory"),
            ("Hickory Sensor", "Hickory"),
            ("Dungeon Cage", "Dungeon"),
        ):
            conn.execute(
                "UPDATE devices SET room_id=? WHERE device_id=?",
                (room_ids[room_name], device_ids[device_name]),
            )

        conn.execute(
            """
            INSERT INTO changelog
                (logtime, ipaddr, device_id, unit, current_values, new_value, agent, comment)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                now - 900,
                "127.0.0.1",
                device_ids["Kitchen"],
                11,
                "AUTO",
                "MID1",
                "screenshot",
                "Synthetic UI screenshot change row",
            ),
        )
        conn.execute(
            """
            INSERT INTO changelog
                (logtime, ipaddr, device_id, unit, current_values, new_value, agent, comment)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                now - 1800,
                "127.0.0.1",
                device_ids["ERV Kitchen"],
                10,
                "MID2",
                "HIGH",
                "rule",
                "Synthetic rule adjustment",
            ),
        )

        conn.execute(
            """
            INSERT INTO alerts (device_id, alert_type, alert_value, start_time, end_time)
            VALUES (?, ?, ?, ?, NULL)
            """,
            (device_ids["Restrooms/BOH"], "FilterSign", "ON", now - 5400),
        )
        conn.execute(
            """
            INSERT INTO alerts (device_id, alert_type, alert_value, start_time, end_time)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                device_ids["ERV Restrooms"],
                "ErrorSign",
                "ON",
                now - 18_000,
                now - 14_400,
            ),
        )

        for index, seconds_ago in enumerate((3600, 6 * 3600, 26 * 3600, 4 * 86400)):
            conn.execute(
                """
                INSERT INTO aqi
                    (logtime, aqi, co, h, no2, o3, p, pm10, pm25, so2, t, w)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now - seconds_ago,
                    42 + index * 8,
                    0.2 + index * 0.03,
                    44 + index,
                    3.0 + index,
                    21 + index * 2,
                    1010 + index,
                    11 + index,
                    5 + index,
                    1.0,
                    21 + index,
                    2.0 + index * 0.2,
                ),
            )

        conn.commit()
        return device_ids
    finally:
        conn.close()


def varied_status(status: dict[str, Any], index: int) -> dict[str, Any]:
    result = copy.deepcopy(status)
    adjust = (index - 1.5) * 0.5
    for key in (TEMPERATURE_KEY, HUMIDITY_KEY, CO2_KEY, VOC_KEY, RADON_KEY, PM25_KEY, PM1_KEY, PRESSURE_KEY):
        raw = result.get(key)
        if isinstance(raw, dict) and VALUE_KEY in raw:
            raw[VALUE_KEY] = round(float(raw[VALUE_KEY]) + adjust, 2)
    attrs = result.get(ATTRIBUTES_KEY)
    if isinstance(attrs, dict):
        for key in (TEMPERATURE_KEY, HUMIDITY_KEY, ILLUMINANCE_KEY):
            if key in attrs and isinstance(attrs[key], (int, float)):
                attrs[key] = round(float(attrs[key]) + adjust, 2)
    if ILLUMINANCE_KEY in result and isinstance(result[ILLUMINANCE_KEY], (int, float)):
        result[ILLUMINANCE_KEY] = round(float(result[ILLUMINANCE_KEY]) + index * 15, 2)
    return result


def install_offline_integrations() -> None:
    from app import ae200
    from app import db
    from app import hubitat
    from app import routes_api

    hubitat.get_all_devices = fake_hubitat_devices
    routes_api.hubitat.get_all_devices = fake_hubitat_devices
    db.weather.get_weather_data = fake_weather_data

    def fake_ae200_devices() -> list[dict[str, str]]:
        return [
            {"id": "10", "name": "ERV Kitchen"},
            {"id": "11", "name": "Kitchen"},
            {"id": "12", "name": "ERV Restrooms"},
            {"id": "13", "name": "Restrooms/BOH"},
            {"id": "14", "name": "Dungeon"},
        ]

    def fake_ae200_device_info(device_id: str | int) -> dict[str, str]:
        return {
            "Group": str(device_id),
            DRIVE_KEY: "ON",
            FAN_SPEED_KEY: "MID2",
            INLET_TEMP_KEY: "21.5",
            SET_TEMP_KEY: "21.0",
            FILTER_SIGN_KEY: "OFF",
            CHECK_WATER_KEY: "OFF",
            ERROR_SIGN_KEY: "OFF",
        }

    ae200.get_devices = fake_ae200_devices
    ae200.get_device_info = fake_ae200_device_info
    routes_api.ae200.get_devices = fake_ae200_devices
    routes_api.ae200.get_device_info = fake_ae200_device_info


def page_specs(device_ids: dict[str, int]) -> list[PageSpec]:
    metric_pages = [
        PageSpec(
            slug=f"metric-{metric_name}",
            title=f"Metric Chart - {metric_name}",
            path=f"/metric_chart?metric={metric_name}",
            wait_selector="#metric-chart canvas",
            settle_ms=900,
        )
        for metric_name in ("humidity", "co2", "voc", "radon", "pm25", "pm1", "pressure")
    ]
    return [
        PageSpec(slug="home", title="Home Dashboard", path="/", wait_selector="#main-grid"),
        PageSpec(slug="air-quality", title="Air Quality", path="/air-quality", wait_selector="#main-grid"),
        PageSpec(
            slug="weather",
            title="Weather",
            path="/weather",
            wait_selector="#weather-current-body .cell-unit",
        ),
        PageSpec(slug="temperature-chart", title="Temperature Chart", path="/chart", wait_selector="#temp-chart canvas"),
        PageSpec(slug="lighting-chart", title="Lighting Chart", path="/lighting_chart", wait_selector="#lighting-chart canvas"),
        *metric_pages,
        PageSpec(slug="aqi-chart", title="Air Quality Chart", path="/chart_aqi", wait_selector="#aqi-chart canvas"),
        PageSpec(slug="alerts", title="Alerts", path="/alerts", wait_selector="#active-alerts-table"),
        PageSpec(slug="rules", title="Rules", path="/rules?run_rules=0", wait_selector=".suspend-rules-buttons"),
        PageSpec(slug="logs-today", title="Activity Log", path="/logs_today", wait_selector="#log-table"),
        PageSpec(slug="logs", title="Detailed Logs", path="/logs", wait_selector="#log-table"),
        PageSpec(slug="all-devices", title="Raw Device Details", path="/all_devices", wait_selector="#db-names-pre:not(.hidden)"),
        PageSpec(slug="kitchen", title="Kitchen Room Dashboard", path="/kitchen?embedded", wait_selector=".device-card"),
        PageSpec(slug="hickory", title="Hickory Room Dashboard", path="/hickory?embedded", wait_selector=".device-card"),
        PageSpec(
            slug="device-log",
            title="Device Log",
            path=f"/device_log/{device_ids['Kitchen']}",
            wait_text_selector="h2",
            wait_text="Device Log",
        ),
        PageSpec(slug="about", title="About", path="/about", wait_selector=".about-content"),
    ]


def free_port(host: str) -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((host, 0))
        return int(sock.getsockname()[1])


def wait_for_server(url: str, timeout: float = 20.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if requests.get(url, timeout=0.5).ok:
                return
        except requests.RequestException:
            pass
        time.sleep(0.1)
    raise RuntimeError(f"Backend not healthy at {url} within {timeout}s")


def start_flask_server(host: str, port: int) -> str:
    from app.main import app

    app.config["TESTING"] = True

    def run_app() -> None:
        app.run(host=host, port=port, debug=False, use_reloader=False)

    server_thread = threading.Thread(target=run_app, daemon=True)
    server_thread.start()
    base_url = f"http://{host}:{port}"
    wait_for_server(f"{base_url}/health")
    return base_url


def render_pages(
    *,
    base_url: str,
    pages: list[PageSpec],
    output_dir: Path,
    width: int,
    height: int,
    timeout_ms: int,
) -> list[RenderedPage]:
    rendered_pages: list[RenderedPage] = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            context = browser.new_context(
                viewport={"width": width, "height": height},
                device_scale_factor=1,
            )
            for spec in pages:
                page = context.new_page()
                console_errors: list[str] = []
                page_errors: list[str] = []
                page.on(
                    "console",
                    lambda msg: console_errors.append(msg.text)
                    if msg.type == "error"
                    else None,
                )
                page.on("pageerror", lambda exc: page_errors.append(str(exc)))
                url = f"{base_url}{spec.path}"
                response = page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
                status = response.status if response else 0
                if status >= 400:
                    raise RuntimeError(f"{spec.path} returned HTTP {status}")
                wait_for_page_ready(page, spec, timeout_ms)
                page.wait_for_timeout(spec.settle_ms)
                filename = f"{spec.slug}.png"
                page.screenshot(path=str(output_dir / filename), full_page=True)
                rendered_pages.append(
                    RenderedPage(
                        slug=spec.slug,
                        title=spec.title,
                        path=spec.path,
                        url=url,
                        filename=filename,
                        status=status,
                        console_errors=console_errors,
                        page_errors=page_errors,
                    )
                )
                page.close()
        finally:
            browser.close()
    return rendered_pages


def wait_for_page_ready(page, spec: PageSpec, timeout_ms: int) -> None:
    try:
        if spec.wait_text_selector and spec.wait_text:
            page.wait_for_function(
                """
                ([selector, text]) => {
                    const el = document.querySelector(selector);
                    return Boolean(el && el.textContent && el.textContent.includes(text));
                }
                """,
                arg=[spec.wait_text_selector, spec.wait_text],
                timeout=timeout_ms,
            )
        elif spec.wait_selector:
            page.wait_for_selector(spec.wait_selector, timeout=timeout_ms)
        try:
            page.wait_for_load_state("networkidle", timeout=2_000)
        except PlaywrightTimeoutError:
            pass
    except PlaywrightTimeoutError as exc:
        raise RuntimeError(f"{spec.path} did not reach expected rendered state") from exc


def write_outputs(manifest: RenderManifest, output_dir: Path) -> None:
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(manifest.model_dump_json(indent=2) + "\n", encoding="utf-8")

    gallery_lines = [
        "# Web UI Screenshots",
        "",
        f"Generated at `{manifest.generated_at}` from `{manifest.base_url}`.",
        "",
    ]
    for page in manifest.pages:
        gallery_lines.extend(
            [
                f"## {page.title}",
                "",
                f"- Route: `{page.path}`",
                f"- HTTP status: `{page.status}`",
                "",
                f"![{page.title}]({page.filename})",
                "",
            ]
        )
        if page.console_errors or page.page_errors:
            gallery_lines.append("<details><summary>Browser errors</summary>")
            gallery_lines.append("")
            for error in page.console_errors + page.page_errors:
                gallery_lines.append(f"- `{error}`")
            gallery_lines.append("")
            gallery_lines.append("</details>")
            gallery_lines.append("")

    (output_dir / "gallery.md").write_text("\n".join(gallery_lines), encoding="utf-8")


def main() -> int:
    args = parse_args()
    output_dir = args.output_dir.resolve()
    prepare_output_dir(output_dir)
    port = args.port or free_port(args.host)

    with tempfile.TemporaryDirectory(prefix="temperature-bot-screenshots-") as tmpdir:
        db_path = Path(tmpdir) / "screenshot.db"
        configure_environment(db_path)

        # Imports that read simulator env vars must happen after environment setup.
        device_ids = create_database(db_path)
        install_offline_integrations()
        base_url = start_flask_server(args.host, port)
        pages = page_specs(device_ids)
        rendered = render_pages(
            base_url=base_url,
            pages=pages,
            output_dir=output_dir,
            width=args.width,
            height=args.height,
            timeout_ms=args.timeout_ms,
        )
        manifest = RenderManifest(
            generated_at=dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat(),
            base_url=base_url,
            viewport_width=args.width,
            viewport_height=args.height,
            pages=rendered,
        )
        write_outputs(manifest, output_dir)

    print(f"Rendered {len(rendered)} pages into {output_dir}")
    for page in rendered:
        print(f"- {page.filename}: {page.path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
