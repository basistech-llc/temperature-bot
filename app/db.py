"""
Centralized database operations to sqlite3 database.
Specialized to temperature bot.
Location is specified by environment variable DB_PATH.
Default location is $ROOT_DIR/temperature-bot.db  (largely for development and testing)

Key concepts:
- For each device, we have:
  - a numeric ID - device_id - we prefer to refer to device by ID
  - a unique name

- For the device log, we have for each device:
  - logtime - the time_t when the log was made last
  - duration - the number of seconds for which it was good
  - temp10x  - an integer with 10x the C temperature
  - status_json - TEXT - if present, a JSON dictionary of all status values (air quality for air quality monitors)

- Air Quality is stored two places:
  - Indoor Air Quality - status_json (right now we don't clearly indicate which devices these are)
  - aqi - outdoor air quality

"""
# pylint: disable=too-many-lines

import sqlite3
import time  # For logtime timestamps
import logging
import json
import math
import os
import sys

from typing import List, Dict, Any

from flask import request

from .constants import (
    DB_PATH,
    DEFAULT_SET_RANGE_CENTER_C,
    MIN_SET_RANGE_C,
    TEMP_SOURCE_STALE_SECONDS,
    TEST_DB_NAME,
)
from .models import (
    AqiSummary,
    AqiWeatherResponse,
    ChangelogResponse,
    ChangelogRow,
    DatabaseColumn,
    DatabaseIndex,
    DatabaseSchemaIssue,
    DatabaseSchemaSnapshot,
    DeviceMetadataControl,
    DeviceStatus,
    FcuSetRange,
    FcuTempSourceControl,
    FcuTempSourceRow,
    FcuTempSourcesResponse,
    Room,
    RoomMap,
    TimeSeries,
    json_ready,
    json_ready_list,
)
from .paths import SCHEMA_FILE_PATH
from .util import github_style_duration
from . import ae200
from . import airquality
from . import weather
from .aq_metrics import (
    AQ_METRIC_STATUS_KEYS,
    extract_metric_from_status,
)

logger = logging.getLogger(__name__)

DEVICE_MAP: dict[str, int] = {}
MAX_DURATION = 3600  # don't extend more than an hour
ROOM_MAP_JSON_KEY = "map_json"
FLYWAY_SCHEMA_HISTORY_TABLE = "flyway_schema_history"
SCHEMA_UPGRADE_COMMAND = "make migrate-db"
DEVICE_TYPE_ERV = "ERV"
DEVICE_TYPE_FCU = "FCU"
FCU_DEFAULT_TEMP_SOURCE_MULTIPLIER = 1.0


def _chart_logtime(row: sqlite3.Row) -> int:
    """Return an integer timestamp for legacy rows that stored float times."""
    return int(row["logtime"])


# Cache the schema file's modification time so we only re-apply the schema
# when the file actually changes on disk. This keeps the convenient
# auto-setup behavior without running the full schema on every request.
# We do this here (rather than at "server startup") because this module
# is also used by CLI tools and schedulers that may not go through a single
# well-defined startup path.
_SCHEMA_MTIME: float | None = None


def reset_schema_mtime_cache() -> None:
    """Reset the schema mtime cache. For use by tests only."""
    global _SCHEMA_MTIME  # pylint: disable=global-statement
    _SCHEMA_MTIME = None


def get_schema_mtime() -> float | None:
    """Return the cached schema mtime. For use by tests only."""
    return _SCHEMA_MTIME


def connect_db(db_path):
    """Establishes a connection to the SQLite database."""
    logger.debug("connect_db(%s)", db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row  # returns rows as dicts
    conn.execute("PRAGMA foreign_keys=ON;")
    # Use DELETE journal mode for testing to avoid WAL locking issues
    if TEST_DB_NAME in os.environ:
        conn.execute("PRAGMA journal_mode=DELETE;")
    else:
        conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    return conn


class DatabaseSchemaMismatchError(RuntimeError):
    """Raised when startup finds a stale or incompatible database schema."""

    def __init__(
        self,
        db_path: str,
        issues: list[DatabaseSchemaIssue],
    ) -> None:
        self.db_path = db_path
        self.issues = issues
        super().__init__(format_schema_mismatch_message(db_path, issues))


def format_schema_mismatch_message(
    db_path: str,
    issues: list[DatabaseSchemaIssue],
) -> str:
    """Return a concise user-facing schema mismatch message."""
    lines = [
        f"Database schema does not match expected application schema: {db_path}",
        (
            "Please upgrade the database before starting Flask. "
            f"Run `{SCHEMA_UPGRADE_COMMAND}`."
        ),
    ]
    if issues:
        lines.append("Schema issues:")
        lines.extend(
            f"- {issue.issue_type} {issue.object_name}: {issue.detail}"
            for issue in issues
        )
    return "\n".join(lines)


def _quote_sqlite_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _normalize_sqlite_type(value: str | None) -> str:
    return (value or "").strip().upper()


def _normalize_sqlite_default(value: object | None) -> str | None:
    return None if value is None else str(value).strip()


def schema_snapshot(conn) -> DatabaseSchemaSnapshot:
    """Return current application tables, columns, and indexes for a database."""
    tables = [
        row[0]
        for row in conn.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type='table'
              AND name NOT LIKE 'sqlite_%'
              AND name <> ?
            ORDER BY name
            """,
            (FLYWAY_SCHEMA_HISTORY_TABLE,),
        ).fetchall()
    ]

    columns: list[DatabaseColumn] = []
    indexes: list[DatabaseIndex] = []
    for table_name in tables:
        quoted_table = _quote_sqlite_identifier(table_name)
        for row in conn.execute(f"PRAGMA table_info({quoted_table})").fetchall():
            columns.append(
                DatabaseColumn(
                    table_name=table_name,
                    column_name=row[1],
                    column_type=_normalize_sqlite_type(row[2]),
                    not_null=bool(row[3]),
                    default_value=_normalize_sqlite_default(row[4]),
                    primary_key=bool(row[5]),
                )
            )
        for row in conn.execute(f"PRAGMA index_list({quoted_table})").fetchall():
            index_name = row[1]
            if not index_name.startswith("sqlite_"):
                indexes.append(
                    DatabaseIndex(
                        table_name=table_name,
                        index_name=index_name,
                        is_unique=bool(row[2]),
                    )
                )

    return DatabaseSchemaSnapshot(
        tables=tables,
        columns=sorted(
            columns,
            key=lambda column: (column.table_name, column.column_name),
        ),
        indexes=sorted(
            indexes,
            key=lambda index: (index.table_name, index.index_name),
        ),
    )


def expected_schema_snapshot(schema_file: str = SCHEMA_FILE_PATH) -> DatabaseSchemaSnapshot:
    """Build the expected schema snapshot from the checked-in schema file."""
    with sqlite3.connect(":memory:") as conn:
        with open(schema_file, "r", encoding="utf-8") as f:
            conn.executescript(f.read())
        return schema_snapshot(conn)


def database_schema_issues(
    conn,
    schema_file: str = SCHEMA_FILE_PATH,
) -> list[DatabaseSchemaIssue]:
    """Compare a database against the checked-in expected schema."""
    expected = expected_schema_snapshot(schema_file)
    actual = schema_snapshot(conn)
    issues: list[DatabaseSchemaIssue] = []

    actual_tables = set(actual.tables)
    expected_tables = set(expected.tables)
    for table_name in sorted(expected_tables - actual_tables):
        issues.append(
            DatabaseSchemaIssue(
                issue_type="missing_table",
                object_name=table_name,
                detail="expected table is missing",
            )
        )

    actual_columns = {
        (column.table_name, column.column_name): column
        for column in actual.columns
    }
    for expected_column in expected.columns:
        if expected_column.table_name not in actual_tables:
            continue
        actual_column = actual_columns.get(
            (expected_column.table_name, expected_column.column_name)
        )
        object_name = f"{expected_column.table_name}.{expected_column.column_name}"
        if actual_column is None:
            issues.append(
                DatabaseSchemaIssue(
                    issue_type="missing_column",
                    object_name=object_name,
                    detail="expected column is missing",
                )
            )
            continue

        mismatches = []
        if actual_column.column_type != expected_column.column_type:
            mismatches.append(
                f"type {actual_column.column_type!r} != {expected_column.column_type!r}"
            )
        if actual_column.not_null != expected_column.not_null:
            mismatches.append(
                f"not_null {actual_column.not_null!r} != {expected_column.not_null!r}"
            )
        if actual_column.default_value != expected_column.default_value:
            mismatches.append(
                "default "
                f"{actual_column.default_value!r} != {expected_column.default_value!r}"
            )
        if actual_column.primary_key != expected_column.primary_key:
            mismatches.append(
                "primary_key "
                f"{actual_column.primary_key!r} != {expected_column.primary_key!r}"
            )
        if mismatches:
            issues.append(
                DatabaseSchemaIssue(
                    issue_type="column_mismatch",
                    object_name=object_name,
                    detail=", ".join(mismatches),
                )
            )

    actual_index_names = {index.index_name for index in actual.indexes}
    for expected_index in expected.indexes:
        if expected_index.table_name not in actual_tables:
            continue
        if expected_index.index_name not in actual_index_names:
            issues.append(
                DatabaseSchemaIssue(
                    issue_type="missing_index",
                    object_name=expected_index.index_name,
                    detail=f"expected index on {expected_index.table_name} is missing",
                )
            )

    return issues


def validate_database_schema(conn, schema_file: str = SCHEMA_FILE_PATH) -> None:
    """Raise if a database does not match the expected application schema."""
    db_path = next(
        (
            row[2]
            for row in conn.execute("PRAGMA database_list").fetchall()
            if row[1] == "main"
        ),
        "<unknown>",
    )
    issues = database_schema_issues(conn, schema_file)
    if issues:
        raise DatabaseSchemaMismatchError(db_path, issues)


def validate_configured_database_schema() -> None:
    """Validate the configured runtime database without modifying its schema."""
    try:
        db_path = (
            os.environ[TEST_DB_NAME]
            if TEST_DB_NAME in os.environ
            else os.environ[DB_PATH]
        )
    except KeyError as e:
        issue = DatabaseSchemaIssue(
            issue_type="missing_config",
            object_name=e.args[0],
            detail="database path environment variable is not set",
        )
        raise DatabaseSchemaMismatchError("<unset>", [issue]) from e

    conn = connect_db(db_path)
    try:
        validate_database_schema(conn)
    finally:
        conn.close()


def get_db_connection():
    """
    Returns a new SQLite connection for each request.
    The connection should be closed by the caller when done.
    Note: We no longer wipe the production database if the schema file's mtime is recent
    """
    try:
        # Use test database if in testing environment
        if "TEST_DB_NAME" in os.environ:
            db_path = os.environ[TEST_DB_NAME]
        else:
            db_path = os.environ[DB_PATH]
        conn = connect_db(db_path)

        # Ensure the database schema is applied for fresh/empty DBs
        # and optionally when the schema file is newer than the DB file.
        needs_schema = False

        try:
            cursor = conn.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' AND name NOT LIKE 'sqlite_%';"
            )
            existing_tables = [row[0] for row in cursor.fetchall()]
            if not existing_tables:
                # Fresh database with no user tables.
                needs_schema = True
        except sqlite3.Error:
            # If we cannot introspect the schema, fall back to applying it.
            needs_schema = True

        if not needs_schema:
            # Best-effort mtime-based schema auto-apply for existing DBs.
            try:
                schema_mtime = os.path.getmtime(SCHEMA_FILE_PATH)
                db_mtime = os.path.getmtime(db_path)
            except OSError:
                schema_mtime = None
                db_mtime = None

            if schema_mtime is not None and db_mtime is not None:
                if schema_mtime > db_mtime:
                    needs_schema = True

        if needs_schema:
            logger.info(
                "Applying database schema from '%s' to '%s'",
                SCHEMA_FILE_PATH,
                db_path,
            )
            setup_database(conn, SCHEMA_FILE_PATH)
        return conn
    except KeyError as e:
        logger.exception("KeyError: %s", e)
        print("*****************************")
        print("*** Please define DB_PATH *** ", file=sys.stderr)
        print("*****************************")
        raise
    except sqlite3.Error as e:
        logger.exception("Database connection error: %s", e)
        raise


def setup_database(conn, schema_file):
    """
    Creates the necessary tables if they don't exist by reading SQL from a file.
    """
    cursor = conn.cursor()

    try:
        with open(schema_file, "r") as f:
            schema_sql = f.read()
        cursor.executescript(schema_sql)  # Executes all SQL statements in the file
        conn.commit()
        DEVICE_MAP.clear()
        logger.info("Database schema from '%s' set up successfully.", schema_file)
    except sqlite3.Error as e:
        conn.rollback()
        logger.error("Database error during schema setup: %s", e)
        raise  # Re-raise the exception
    except Exception as e:
        conn.rollback()
        logger.exception("An unexpected error occurred during schema setup: %s", e)
        raise


################################################################
## Device management


def get_or_create_device_id(conn, device_name, use_cache=True):
    """
    Retrieves the ID for a given device name. If the device name does not exist
    in the devices table, it inserts it and returns the newly generated ID.
    Don't use the cache when testing
    """
    cursor = conn.cursor()

    if "PYTEST" in os.environ:
        use_cache = False

    if use_cache and (device_name in DEVICE_MAP):
        logger.debug(
            "get_or_create_device_id DEVICE_MAP[%s]=%s",
            device_name,
            DEVICE_MAP[device_name],
        )
        return DEVICE_MAP[device_name]

    try:
        logger.debug("INSERT OR IGNORE device_name=%s", device_name)
        cursor.execute(
            "INSERT OR IGNORE INTO devices (device_name) VALUES (?);", (device_name,)
        )
        conn.commit()

        cursor.execute("SELECT * FROM devices WHERE device_name = ?;", (device_name,))
        result = cursor.fetchone()

        if result:
            logger.debug(
                "get_or_create_device_id(%s) result=%s", device_name, dict(result)
            )
            DEVICE_MAP[device_name] = result["device_id"]
            return DEVICE_MAP[device_name]
        else:
            logger.error("Could not retrieve ID for device name: %s", device_name)
            raise ValueError("Could not retrieve ID for device name: %s" % device_name)  # pylint: disable=consider-using-f-string

    except sqlite3.Error as e:
        logger.error("Database error in get_or_create_device_id: %s", e)
        conn.rollback()  # Rollback any partial transaction
        raise  # Re-raise the exception


def fetch_all_devices(conn):
    """Fetches all device names and their IDs."""
    cursor = conn.cursor()
    cursor.execute("SELECT id, name FROM devices;")
    return cursor.fetchall()


def fetch_all_device_dicts(conn):
    """Fetches all device names and their IDs."""
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM devices;")
    return cursor.fetchall()


def get_device(conn, device_id: int) -> dict[str, Any] | None:
    c = conn.cursor()
    c.execute("SELECT * FROM devices WHERE device_id=?", (device_id,))
    row = c.fetchone()
    return dict(row) if row else None


def normalize_device_type(device_type: object) -> str | None:
    if not isinstance(device_type, str):
        return None
    normalized = device_type.strip().upper()
    return normalized or None


def infer_device_type(devdict: dict[str, Any]) -> str | None:
    configured = normalize_device_type(devdict.get("device_type"))
    if configured:
        return configured
    if not devdict.get("has_speed_control"):
        return None
    name = devdict.get("device_name", "")
    if isinstance(name, str) and name.lower().startswith("erv"):
        return DEVICE_TYPE_ERV
    return DEVICE_TYPE_FCU


def get_device_metadata(conn) -> list[dict[str, Any]]:
    """Return editable device catalog rows."""
    c = conn.cursor()
    c.execute(
        """
        SELECT d.device_id, d.device_name, d.display_name, d.device_type,
               d.rules_enabled, d.ae200_device_id, d.disabled_until,
               d.notes, d.aqi_mon, d.room_id, r.room_name
        FROM devices d
        LEFT JOIN rooms r ON d.room_id = r.room_id
        ORDER BY d.device_name
        """
    )
    return [_normalize_device_metadata_row(dict(row)) for row in c.fetchall()]


def _normalize_device_metadata_row(item: dict[str, Any]) -> dict[str, Any]:
    item["device_type"] = normalize_device_type(item.get("device_type"))
    item["rules_enabled"] = bool(item.get("rules_enabled", True))
    return item


def update_device_metadata(
    conn,
    body: DeviceMetadataControl,
    *,
    fields: set[str] | None = None,
) -> dict[str, Any]:
    """Update editable device metadata and return the updated row."""
    update_fields = fields or {"display_name", "device_type", "rules_enabled", "notes"}
    assignments = []
    args: list[Any] = []
    if "display_name" in update_fields:
        assignments.append("display_name=?")
        args.append(body.display_name)
    if "device_type" in update_fields:
        assignments.append("device_type=?")
        args.append(normalize_device_type(body.device_type))
    if "rules_enabled" in update_fields and body.rules_enabled is not None:
        assignments.append("rules_enabled=?")
        args.append(1 if body.rules_enabled else 0)
    if "notes" in update_fields:
        assignments.append("notes=?")
        args.append(body.notes)
    if not assignments:
        device = get_device(conn, body.device_id)
        if device is None:
            raise ValueError(f"Unknown device_id: {body.device_id}")
        return _normalize_device_metadata_row(device)

    args.append(body.device_id)
    c = conn.cursor()
    c.execute(
        f"UPDATE devices SET {', '.join(assignments)} WHERE device_id=?",
        args,
    )
    if c.rowcount == 0:
        raise ValueError(f"Unknown device_id: {body.device_id}")
    conn.commit()
    updated = get_device(conn, body.device_id)
    assert updated is not None
    return _normalize_device_metadata_row(updated)


def devices_to_device_id(conn):
    """Return a dictionary of device_name:device_id"""
    c = conn.cursor()
    c.execute("SELECT * from devices order by device_name")
    ret = {
        dev["device_name"].replace(" ", "_").upper(): dev["device_id"]
        for dev in c.fetchall()
    }
    logging.debug("ret=%s", ret)
    return ret


################################################################
## Room metadata


def _room_map_from_json(map_json: str | None) -> RoomMap | None:
    try:
        data = json.loads(map_json or "{}")
    except json.JSONDecodeError:
        data = {}
    if not data:
        return None
    return RoomMap.model_validate(data)


def _room_from_row(row: sqlite3.Row) -> Room:
    return Room(
        room_id=row["room_id"],
        room_name=row["room_name"],
        map=_room_map_from_json(row[ROOM_MAP_JSON_KEY]),
    )


def get_rooms(conn) -> list[Room]:
    c = conn.cursor()
    c.execute("SELECT * FROM rooms ORDER BY room_name")
    return [_room_from_row(row) for row in c.fetchall()]


def get_room(conn, room_id: int) -> Room | None:
    c = conn.cursor()
    c.execute("SELECT * FROM rooms WHERE room_id=?", (room_id,))
    row = c.fetchone()
    if row is None:
        return None
    return _room_from_row(row)


def create_room(conn, room: Room) -> Room:
    if room.room_name is None:
        raise ValueError("room_name is required")
    c = conn.cursor()
    if room.map is None:
        c.execute("INSERT INTO rooms (room_name) VALUES (?)", (room.room_name,))
    else:
        c.execute(
            "INSERT INTO rooms (room_name, map_json) VALUES (?, ?)",
            (room.room_name, room.map.model_dump_json(exclude_none=True)),
        )
    conn.commit()
    created = get_room(conn, int(c.lastrowid))
    assert created is not None
    return created


def update_room(conn, room: Room) -> Room | None:
    if room.room_id is None:
        raise ValueError("room_id is required")
    assignments = []
    args: list[Any] = []
    if room.room_name is not None:
        assignments.append("room_name=?")
        args.append(room.room_name)
    if room.map is not None:
        assignments.append("map_json=?")
        args.append(room.map.model_dump_json(exclude_none=True))
    if not assignments:
        return get_room(conn, room.room_id)
    args.append(room.room_id)

    c = conn.cursor()
    c.execute(
        f"UPDATE rooms SET {', '.join(assignments)} WHERE room_id=?",
        args,
    )
    if c.rowcount == 0:
        return None
    conn.commit()
    return get_room(conn, room.room_id)


def update_device_room(conn, device_id: int, room_id: int | None) -> int:
    c = conn.cursor()
    if room_id is not None:
        c.execute("SELECT 1 FROM rooms WHERE room_id=?", (room_id,))
        if c.fetchone() is None:
            raise ValueError(f"Unknown room_id: {room_id}")
    c.execute("UPDATE devices SET room_id=? WHERE device_id=?", (room_id, device_id))
    if c.rowcount == 0:
        raise ValueError(f"Unknown device_id: {device_id}")
    conn.commit()
    return device_id


EVERY_DEVICE=1
AIR_MON_DEVICES=2
def fetch_last_status(conn, flag=EVERY_DEVICE):
    """Fetches the last status for every device. Specify where to restrict which devices are returned"""
    if flag==AIR_MON_DEVICES:
        where = "b.aqi_mon = 1"
    else:
        where = "1=1"
    cursor = conn.cursor()
    cursor.execute(f"""
        SELECT a.*,b.device_name,b.display_name,b.device_type,b.rules_enabled,
               b.ae200_device_id,b.notes,b.disabled_until,b.room_id,r.room_name
        FROM (SELECT * FROM devlog GROUP BY device_id HAVING logtime=max(logtime)) AS a
        JOIN devices b ON a.device_id = b.device_id
        LEFT JOIN rooms r ON b.room_id = r.room_id
        WHERE {where}
        ORDER by b.device_name""")
    return cursor.fetchall()


def fetch_last_status_fixed(conn, flag=EVERY_DEVICE):
    """Runs db.fetch_last_status(conn) and then converts `status_json` into the actual dictionary for each status_json object"""

    def fix_status_json(devdict):
        devdict = dict(devdict)
        try:
            devdict["status"] = json.loads(devdict["status_json"])
        except (TypeError, json.JSONDecodeError):
            pass
        del devdict["status_json"]
        return devdict

    return [fix_status_json(dd) for dd in fetch_last_status(conn, flag=flag)]


################################################################
## devlog - log of what happened


def fetch_all_devlog_with_devices(conn):
    """
    Fetches all devlog entries, joining with devices to display the device string.
    """
    cursor = conn.cursor()
    cursor.execute("""
        SELECT
            t.id, t.logtime, s.name AS device_name, t.temp10x, s.notes
        FROM
            devlog t
        JOIN
            devices s ON t.device_id = s.device_id
        ORDER BY
            t.logtime DESC;
    """)
    return cursor.fetchall()


def get_recent_devlogs(conn, device_name: str, seconds: int):
    """
    Get recent devlog entries for a device within the specified time window.

    :param conn: database connection
    :param device_name: the device name to query
    :param seconds: number of seconds to look back from now
    :return: list of devlog entries where logtime+duration > now()-seconds
    """
    cursor = conn.cursor()
    current_time = int(time.time())
    cutoff_time = current_time - seconds

    try:
        # Get the device_id
        device_id = get_or_create_device_id(conn, device_name)

        # Query for entries where logtime+duration > cutoff_time
        # This ensures we get the most recent entry AND any other entry that overlaps with our time window
        cursor.execute(
            """
            SELECT d.*, dn.device_name
            FROM devlog d
            JOIN devices dn ON d.device_id = dn.device_id
            WHERE d.device_id = ? AND (d.logtime + d.duration) > ?
            ORDER BY d.logtime DESC
        """,
            (device_id, cutoff_time),
        )

        return cursor.fetchall()

    except sqlite3.Error as e:
        logger.error("Database error in get_recent_devlogs: %s", e)
        raise
    except ValueError as e:
        logger.error("Error: %s", e)
        raise


# Insertion
# pylint: disable=too-many-arguments, disable=too-many-positional-arguments
def insert_devlog_entry(
    conn,
    *,
    device_id=None,
    device_name: str | None = None,
    temp=None,
    statusdict=None,
    logtime=None,
    force=False,
    commit=True,
):
    """
    :param conn: database connection
    :param device_id: the device_id
    :param device_name: the device (if device_id is not provided)
    :param temp: Temperature in C
    :param statusdict: If provided, a dictionary that will be written to the database as status_json (but not if extending)
    :param logtime: The time_t of the log. If not provided, it's now!
    :param force: If True, forces a new entry.
                  If False, then only create a new entry if the temp or statusdict have changed.
    Inserts an entry into the devlog table, handling the device_id lookup/creation and automatic extension.
    """
    logger.debug(
        "device_id=%s device_name=%s temp=%s logtime=%s force=%s commit=%s",
        device_id,
        device_name,
        temp,
        logtime,
        force,
        commit,
    )
    temp10x = int(math.floor(float(temp) * 10 + 0.5)) if temp else None
    status_json = (
        json.dumps(statusdict, default=str, sort_keys=True) if statusdict else None
    )
    c = conn.cursor()
    if logtime is None:
        logtime = int(time.time())  # Use current Unix timestamp if not provided
    else:
        logtime = int(logtime)
    try:
        # Get or create the device_id
        if device_id is None:
            assert device_name is not None
            device_id = get_or_create_device_id(conn, device_name)

        # Get the most recent temperature entry. If temperature matches and we are not forcing, extend it.
        c.execute(
            "SELECT * from devlog where device_id=? and logtime<=? order by logtime DESC limit 1",
            (device_id, logtime),
        )
        r = c.fetchone()
        if r and r["logtime"] == logtime:
            # duplicate entry. Replace if duration is 1
            if r["duration"] == 1:
                logger.debug("replace with temp10x=%s status=%s", temp10x, status_json)
                c.execute(
                    "UPDATE devlog set temp10x=?,status_json=? where log_id=?",
                    (temp10x, status_json, r["log_id"]),
                )
            else:
                logger.debug(
                    "ignore temp10x=%s status=%s because row=%s",
                    temp10x,
                    status_json,
                    dict(r),
                )
            return

        if (
            r
            and r["temp10x"] == temp10x
            and r["status_json"] == status_json
            and not force
        ):
            row_logtime = int(r["logtime"])
            duration = logtime - row_logtime + 1
            if duration < MAX_DURATION:
                logger.info(
                    "Updated devlog entry: device_id=%s temp10x=%s logtime=%s duration=%s",
                    device_id,
                    temp10x,
                    time.asctime(time.localtime(row_logtime)),
                    duration,
                )
                c.execute(
                    "UPDATE devlog set duration=? where log_id=?",
                    (duration, r["log_id"]),
                )
                if commit:
                    conn.commit()
                return

        # Insert into devlog using the obtained device_id
        logger.debug("insert logtime=%s device_id=%s", logtime, device_id)
        c.execute(
            "INSERT INTO devlog (logtime, device_id, temp10x, status_json) VALUES (?, ?, ?, ?);",
            (logtime, device_id, temp10x, status_json),
        )
        if commit:
            conn.commit()
        logger.info(
            "Inserted devlog entry: device_id=%s, temp10x=%s", device_id, temp10x
        )
    except sqlite3.Error as e:
        logger.error("Database error in insert_devlog_entry: %s", e)
        conn.rollback()  # Rollback any partial transaction
        raise
    except ValueError as e:
        logger.error("Error: %s", e)
        conn.rollback()
        raise


def insert_changelog(
    conn,
    *,
    ipaddr: str,
    device_id: int,
    ae200_device_id: int | None,
    current_values: str = "",
    new_value: str,
    agent: str = "",
    comment: str = "",
    commit: bool = True,
):
    logtime = int(time.time())
    c = conn.cursor()
    c.execute(
        """
        INSERT INTO changelog (logtime, ipaddr, device_id, unit, current_values, new_value, agent, comment)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            logtime,
            ipaddr,
            device_id,
            ae200_device_id,
            current_values,
            new_value,
            agent,
            comment,
        ),
    )
    if commit:
        conn.commit()


def update_devlog_map(conn, device_name: str, ae200_device_id: int):
    logger.debug("device_name=%s ae200_device_id=%s", device_name, ae200_device_id)
    c = conn.cursor()
    device_id = get_or_create_device_id(conn, device_name)
    c.execute(
        "UPDATE devices set ae200_device_id = ? where device_id=?",
        (ae200_device_id, device_id),
    )
    conn.commit()
    return device_id


################################################################
## Rules
def device_rules_disabled_until(conn, device_id: int) -> int | None:
    """
    :param conn: - database connection
    :param device_id: - device_id
    :return: time_t that rules are disabled until, or None if they are no longer disabled
    """
    c = conn.cursor()
    c.execute("SELECT disabled_until from devices where device_id=?", (device_id,))
    row = c.fetchone()
    return row[0] if row is not None else None


def get_rules_master_enabled(conn) -> bool:
    """
    Return True if the global master rules switch is enabled, False if disabled.

    This uses a dedicated RULES_MASTER pseudo-device's disabled_until field as
    the underlying storage, so we can distinguish it from time-limited rules
    disablement on the rules_engine device.
    """
    device_id = get_or_create_device_id(conn, "rules_master")
    disabled_until = device_rules_disabled_until(conn, device_id)
    # When disabled_until is 0 or in the past, rules are enabled.
    if not disabled_until:
        return True
    return disabled_until <= int(time.time())


def set_rules_master_enabled(conn, enabled: bool):
    """
    Set the global master rules switch enabled/disabled using the RULES_MASTER
    pseudo-device's disabled_until.
    """
    device_id = get_or_create_device_id(conn, "rules_master")
    now = int(time.time())
    if enabled:
        until = 0
    else:
        # Use a far-future timestamp (~10 years) to represent "off until changed".
        until = now + 10 * 365 * 24 * 60 * 60

    c = conn.cursor()
    c.execute(
        "UPDATE devices set disabled_until=? where device_id=?", (until, device_id)
    )
    # Also record in changelog for audit/history purposes.
    c.execute(
        """
        INSERT INTO changelog (logtime, ipaddr, device_id, current_values, new_value, agent, comment)
        VALUES (?,?,?,?,?,?,?)
        """,
        (
            now,
            None,
            device_id,
            None,
            until,
            "web",
            "master rules switch " + ("enabled" if enabled else "disabled"),
        ),
    )
    conn.commit()


def disable_rules_for_device(
    conn, device_id: int, seconds: int, ipaddr=None, agent=None, comment=None
):
    """Disable the rules for this device for a given number of seconds."""
    now = int(time.time())
    if seconds == 0:
        until = 0
    else:
        until = now + seconds
    c = conn.cursor()

    # Get the old value
    c.execute("SELECT disabled_until from devices where device_id=?", (device_id,))
    was = c.fetchone()
    current_value = was[0] if was else None

    # Update the disabled until and then the changelog
    c.execute(
        "UPDATE devices set disabled_until=? where device_id=?", (until, device_id)
    )

    # Write the log entry
    c.execute(
        """
        INSERT INTO changelog (logtime, ipaddr, device_id, current_values, new_value, agent, comment)
        VALUES (?,?,?,?,?,?,?)
        """,
        (now, ipaddr, device_id, current_value, until, agent, comment),
    )
    conn.commit()


def update_device_notes(conn, device_id: int, notes: str | None):
    """Update the notes field for a device."""
    logger.debug("update_device_notes: device_id=%s, notes=%s", device_id, notes)
    c = conn.cursor()
    c.execute("UPDATE devices SET notes=? WHERE device_id=?", (notes, device_id))
    conn.commit()
    return device_id


################################################################
## AE200
AE200_SIMULATOR_STATUS_KEYS = frozenset(
    {
        ae200.AE200_DRIVE_KEY,
        ae200.AE200_FAN_SPEED_KEY,
        ae200.AE200_MODE_KEY,
        "InletTemp",
        "SetTemp",
    }
)


def _ae200_simulator_name_key(name: str | None) -> str:
    return "".join(ch for ch in (name or "").casefold() if ch.isalnum())


def _latest_status_for_device(conn, device_id: int) -> dict[str, Any] | None:
    c = conn.cursor()
    c.execute(
        """
        SELECT status_json
        FROM devlog
        WHERE device_id=?
        ORDER BY logtime DESC
        LIMIT 1
        """,
        (device_id,),
    )
    row = c.fetchone()
    if row is None:
        return None
    try:
        status = json.loads(row["status_json"] or "{}")
    except json.JSONDecodeError:
        return None
    return status if isinstance(status, dict) else None


def _looks_like_ae200_status(status: dict[str, Any] | None) -> bool:
    return bool(status and AE200_SIMULATOR_STATUS_KEYS.intersection(status))


def _ae200_simulator_unit_for_device(
    conn,
    device_id: int,
    device_name: str,
    ae200_device_id: int | None,
) -> int:
    simulator_devices = ae200.get_devices()
    configured_id = str(ae200_device_id) if ae200_device_id is not None else None
    simulator_ids = {str(device["id"]) for device in simulator_devices}
    if configured_id in simulator_ids:
        return int(configured_id)

    latest_status = _latest_status_for_device(conn, device_id)
    if configured_id is not None and _looks_like_ae200_status(latest_status):
        ae200.register_simulated_device(
            ae200_device=ae200_device_id,
            name=device_name,
            statusdict=latest_status,
        )
        logger.info(
            "AE-200 simulator registered local device_id=%s name=%s configured_unit=%s",
            device_id,
            device_name,
            ae200_device_id,
        )
        return int(configured_id)

    device_name_key = _ae200_simulator_name_key(device_name)
    for simulator_device in simulator_devices:
        if _ae200_simulator_name_key(simulator_device.get("name")) == device_name_key:
            simulator_id = int(simulator_device["id"])
            logger.info(
                "AE-200 simulator mapped device_id=%s name=%s configured_unit=%s to simulator_unit=%s",
                device_id,
                device_name,
                ae200_device_id,
                simulator_id,
            )
            return simulator_id

    raise ValueError(
        "AE-200 simulator has no unit for "
        f"device_id={device_id} name={device_name!r} "
        f"configured ae200_device_id={ae200_device_id}; "
        f"simulator units={sorted(simulator_ids)}"
    )


def get_ae200_unit(conn, device_id: int):
    c = conn.cursor()
    c.execute(
        "select device_name, ae200_device_id from devices where device_id=?",
        (device_id,),
    )
    row = c.fetchone()
    if row is None:
        raise ValueError(f"Unknown device_id={device_id}")

    ae200_device_id = row["ae200_device_id"]
    if ae200.AE200_SIMULATOR:
        ret = _ae200_simulator_unit_for_device(
            conn,
            device_id=device_id,
            device_name=row["device_name"],
            ae200_device_id=ae200_device_id,
        )
    elif ae200_device_id is None:
        raise ValueError(f"Device {device_id} has no ae200_device_id")
    else:
        ret = ae200_device_id

    logger.debug("device_id=%s ae200_unit=%s", device_id, ret)
    return ret


################################################################
## AQI and Temperature


def temporal_quantification(cmd, args):
    """Annotate cmd and args with start, end, limit"""
    start = request.args.get("start", type=int)
    end = request.args.get("end", type=int)

    if start is not None:
        cmd += " AND logtime >= ? "
        args.append(start)

    if end is not None:
        cmd += " AND logtime <= ? "
        args.append(end)

    return (cmd, args)


################################################################
## AQI
def get_last_aqi(conn):
    c = conn.cursor()
    c.execute("select aqi from aqi order by logtime DESC limit 1")
    row = c.fetchone()
    if row is None:
        logger.warning("No AQI data available; defaulting to 50")
        return 50
    aqi = row[0]
    logger.debug("last_aqi=%s", aqi)
    return aqi


def get_aqi_series(conn):
    c = conn.cursor()
    cmd = """ SELECT * from aqi where 1 """
    (cmd, args) = temporal_quantification(cmd, [])
    cmd += " ORDER BY logtime "
    c.execute(cmd, args)
    rows = c.fetchall()
    if not rows:
        return []
    keys = [k for k in rows[0].keys() if k != "logtime"]
    return {key: [[row["logtime"], row[key]] for row in rows] for key in keys}


def is_erv_device(devdict: dict[str, Any]) -> bool:
    device_type = normalize_device_type(devdict.get("device_type"))
    if device_type:
        return device_type == DEVICE_TYPE_ERV
    return bool(devdict.get("has_speed_control")) and devdict.get(
        "device_name", ""
    ).lower().startswith("erv")


def is_fcu_device(devdict: dict[str, Any]) -> bool:
    device_type = normalize_device_type(devdict.get("device_type"))
    if device_type:
        return device_type == DEVICE_TYPE_FCU
    return bool(devdict.get("has_speed_control")) and not is_erv_device(devdict)


def _float_or_none(value: object) -> float | None:
    try:
        if value is None or value == "":
            return None
        if not isinstance(value, (int, float, str)):
            return None
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _set_temp_c_from_status(status: dict[str, Any] | None) -> float | None:
    if not isinstance(status, dict):
        return None
    return _float_or_none(status.get("SetTemp"))


def _latest_set_temp_c_for_device(conn, device_id: int) -> float | None:
    c = conn.cursor()
    c.execute(
        """
        SELECT status_json
        FROM devlog
        WHERE device_id=?
        ORDER BY logtime DESC
        LIMIT 1
        """,
        (device_id,),
    )
    row = c.fetchone()
    if row is None:
        return None
    try:
        status = json.loads(row["status_json"] or "{}")
    except json.JSONDecodeError:
        return None
    return _set_temp_c_from_status(status)


def _round_temp_c(value: float) -> float:
    return round(float(value), 1)


def _validated_set_range_values(low_c: float, high_c: float) -> tuple[float, float]:
    low = _round_temp_c(low_c)
    high = _round_temp_c(high_c)
    if not math.isfinite(low) or not math.isfinite(high):
        raise ValueError("set range endpoints must be finite Celsius values")
    if high - low < MIN_SET_RANGE_C:
        raise ValueError(f"set range must be at least {MIN_SET_RANGE_C:g} C wide")
    return low, high


def default_fcu_set_range(device_id: int, set_temp_c: float | None) -> FcuSetRange:
    """Return the effective default FCU set range before a row is persisted."""
    center = set_temp_c if set_temp_c is not None else DEFAULT_SET_RANGE_CENTER_C
    half_range = MIN_SET_RANGE_C / 2
    return FcuSetRange(
        device_id=device_id,
        set_range_low_c=_round_temp_c(center - half_range),
        set_range_high_c=_round_temp_c(center + half_range),
        min_set_range_c=MIN_SET_RANGE_C,
    )


def _fcu_set_range_from_row(row: sqlite3.Row) -> FcuSetRange:
    return FcuSetRange(
        device_id=row["fcu_device_id"],
        set_range_low_c=row["set_range_low_c"],
        set_range_high_c=row["set_range_high_c"],
        min_set_range_c=MIN_SET_RANGE_C,
        updated_at=row["updated_at"],
    )


def get_fcu_set_ranges(conn, fcu_device_ids: list[int]) -> dict[int, FcuSetRange]:
    """Return persisted set ranges keyed by FCU device id."""
    if not fcu_device_ids:
        return {}
    wanted_values = ",".join(["(?)"] * len(fcu_device_ids))
    c = conn.cursor()
    c.execute(
        f"""
        WITH wanted(fcu_device_id) AS (VALUES {wanted_values})
        SELECT r.*
        FROM fcu_set_ranges r
        JOIN wanted w ON r.fcu_device_id = w.fcu_device_id
        """,
        fcu_device_ids,
    )
    return {
        row["fcu_device_id"]: _fcu_set_range_from_row(row) for row in c.fetchall()
    }


def get_fcu_set_range(
    conn, device_id: int, set_temp_c: float | None = None
) -> FcuSetRange:
    """Return the persisted FCU set range, or the current effective default."""
    c = conn.cursor()
    c.execute(
        """
        SELECT *
        FROM fcu_set_ranges
        WHERE fcu_device_id=?
        """,
        (device_id,),
    )
    row = c.fetchone()
    if row is not None:
        return _fcu_set_range_from_row(row)
    return default_fcu_set_range(device_id, set_temp_c)


def _format_set_range(low_c: float, high_c: float) -> str:
    return f"{low_c:g}-{high_c:g}"


def set_fcu_set_range(
    conn,
    *,
    device_id: int,
    set_range_low_c: float,
    set_range_high_c: float,
    ipaddr: str | None,
    agent: str | None,
) -> dict[str, Any]:
    """Persist one FCU set range and log effective old/new values."""
    fcu = get_device(conn, device_id)
    if fcu is None:
        raise ValueError(f"Unknown device_id: {device_id}")

    new_low, new_high = _validated_set_range_values(
        set_range_low_c,
        set_range_high_c,
    )
    c = conn.cursor()
    c.execute(
        """
        SELECT *
        FROM fcu_set_ranges
        WHERE fcu_device_id=?
        """,
        (device_id,),
    )
    row = c.fetchone()
    old_range = (
        _fcu_set_range_from_row(row)
        if row is not None
        else default_fcu_set_range(device_id, _latest_set_temp_c_for_device(conn, device_id))
    )
    changed = (
        old_range.set_range_low_c != new_low
        or old_range.set_range_high_c != new_high
    )
    if row is not None and not changed:
        return json_ready(old_range)

    now = int(time.time())
    c.execute(
        """
        INSERT INTO fcu_set_ranges
            (fcu_device_id, set_range_low_c, set_range_high_c, updated_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(fcu_device_id)
        DO UPDATE SET
            set_range_low_c=excluded.set_range_low_c,
            set_range_high_c=excluded.set_range_high_c,
            updated_at=excluded.updated_at
        """,
        (device_id, new_low, new_high, now),
    )

    if changed:
        insert_changelog(
            conn,
            ipaddr=ipaddr or "",
            device_id=device_id,
            ae200_device_id=fcu.get("ae200_device_id"),
            current_values=_format_set_range(
                old_range.set_range_low_c,
                old_range.set_range_high_c,
            ),
            new_value=_format_set_range(new_low, new_high),
            agent=agent or "",
            comment="set range",
        )
    else:
        conn.commit()

    return json_ready(
        FcuSetRange(
            device_id=device_id,
            set_range_low_c=new_low,
            set_range_high_c=new_high,
            min_set_range_c=MIN_SET_RANGE_C,
            updated_at=now,
        )
    )


def get_fcu_temp_source_weights(conn, fcu_device_id: int) -> dict[int, float]:
    """Return source weights for one FCU, applying the FCU default if absent."""
    rows = _fcu_temp_source_weight_rows(conn, fcu_device_id)
    weights = {}
    for row in rows:
        weights[row["source_device_id"]] = float(row["multiplier"])
    if fcu_device_id not in weights:
        weights[fcu_device_id] = FCU_DEFAULT_TEMP_SOURCE_MULTIPLIER
    return weights


def _fcu_temp_source_weight_rows(conn, fcu_device_id: int):
    c = conn.cursor()
    c.execute(
        """
        SELECT source_device_id, multiplier
        FROM fcu_temp_sources
        WHERE fcu_device_id=?
        """,
        (fcu_device_id,),
    )
    return c.fetchall()


def _latest_temperature_source_rows(conn, fcu_device_id: int, now: int):
    weights = get_fcu_temp_source_weights(conn, fcu_device_id)
    c = conn.cursor()
    c.execute(
        """
        SELECT
            d.device_id AS source_device_id,
            d.device_name,
            d.room_id,
            r.room_name,
            l.logtime,
            l.duration,
            l.temp10x
        FROM (
            SELECT d1.*
            FROM devlog d1
            JOIN (
                SELECT device_id, MAX(logtime) AS max_logtime
                FROM devlog
                WHERE temp10x IS NOT NULL
                GROUP BY device_id
            ) latest
                ON d1.device_id = latest.device_id
                AND d1.logtime = latest.max_logtime
        ) l
        JOIN devices d ON d.device_id = l.device_id
        LEFT JOIN rooms r ON d.room_id = r.room_id
        ORDER BY d.device_name
        """
    )
    rows = []
    for row in c.fetchall():
        age_seconds = int(
            max(0, now - (float(row["logtime"]) + float(row["duration"] or 0)))
        )
        is_stale = age_seconds > TEMP_SOURCE_STALE_SECONDS
        multiplier = weights.get(row["source_device_id"], 0.0)
        rows.append(
            FcuTempSourceRow(
                source_device_id=row["source_device_id"],
                device_name=row["device_name"],
                room_id=row["room_id"],
                room_name=row["room_name"],
                is_fcu_self=row["source_device_id"] == fcu_device_id,
                temp10x=row["temp10x"],
                age_seconds=age_seconds,
                is_stale=is_stale,
                multiplier=multiplier,
                included=multiplier > 0 and not is_stale,
            )
        )
    return rows


def get_fcu_temp_sources(conn, fcu_device_id: int) -> dict[str, Any]:
    if get_device(conn, fcu_device_id) is None:
        raise ValueError(f"Unknown fcu_device_id: {fcu_device_id}")
    sources = _latest_temperature_source_rows(conn, fcu_device_id, int(time.time()))
    return json_ready(
        FcuTempSourcesResponse(
            fcu_device_id=fcu_device_id,
            stale_seconds=TEMP_SOURCE_STALE_SECONDS,
            sources=sources,
        )
    )


def _temperature_row_for_source(conn, source_device_id: int, at_time: int | None):
    c = conn.cursor()
    if at_time is None:
        c.execute(
            """
            SELECT logtime, duration, temp10x
            FROM devlog
            WHERE device_id=? AND temp10x IS NOT NULL
            ORDER BY logtime DESC
            LIMIT 1
            """,
            (source_device_id,),
        )
    else:
        c.execute(
            """
            SELECT logtime, duration, temp10x
            FROM devlog
            WHERE device_id=? AND temp10x IS NOT NULL AND logtime <= ?
            ORDER BY logtime DESC
            LIMIT 1
            """,
            (source_device_id, at_time),
        )
    return c.fetchone()


def calculate_fcu_temperature10x(
    conn, fcu_device_id: int, at_time: int | None = None
) -> int | None:
    weights = get_fcu_temp_source_weights(conn, fcu_device_id)

    now = int(time.time()) if at_time is None else at_time
    weighted_total = 0.0
    weight_total = 0.0
    for source_device_id, multiplier in weights.items():
        if multiplier <= 0:
            continue
        temp_row = _temperature_row_for_source(conn, source_device_id, at_time)
        if temp_row is None:
            continue
        last_valid = temp_row["logtime"] + temp_row["duration"]
        if now - last_valid > TEMP_SOURCE_STALE_SECONDS:
            continue
        weighted_total += temp_row["temp10x"] * multiplier
        weight_total += multiplier

    if weight_total <= 0:
        return None
    return int(math.floor((weighted_total / weight_total) + 0.5))


def _fcu_temp_source_weights_for_fcus(
    conn, fcu_device_ids: list[int]
) -> dict[int, dict[int, float]]:
    weights_by_fcu = {
        fcu_device_id: {fcu_device_id: FCU_DEFAULT_TEMP_SOURCE_MULTIPLIER}
        for fcu_device_id in fcu_device_ids
    }
    if not fcu_device_ids:
        return weights_by_fcu

    wanted_values = ",".join(["(?)"] * len(fcu_device_ids))
    c = conn.cursor()
    c.execute(
        f"""
        WITH wanted(fcu_device_id) AS (VALUES {wanted_values})
        SELECT s.fcu_device_id, s.source_device_id, s.multiplier
        FROM fcu_temp_sources s
        JOIN wanted w ON s.fcu_device_id = w.fcu_device_id
        """,
        fcu_device_ids,
    )
    for row in c.fetchall():
        weights_by_fcu[row["fcu_device_id"]][row["source_device_id"]] = float(
            row["multiplier"]
        )
    return weights_by_fcu


def _latest_temperature_rows_by_source(
    conn, source_device_ids: list[int]
) -> dict[int, sqlite3.Row]:
    if not source_device_ids:
        return {}

    wanted_values = ",".join(["(?)"] * len(source_device_ids))
    c = conn.cursor()
    c.execute(
        f"""
        WITH wanted(device_id) AS (VALUES {wanted_values}),
        latest AS (
            SELECT d.device_id, MAX(d.logtime) AS logtime
            FROM devlog d
            JOIN wanted w ON d.device_id = w.device_id
            WHERE d.temp10x IS NOT NULL
            GROUP BY d.device_id
        )
        SELECT d.device_id, d.logtime, d.duration, d.temp10x
        FROM devlog d
        JOIN latest l
            ON d.device_id = l.device_id
            AND d.logtime = l.logtime
        WHERE d.temp10x IS NOT NULL
        """,
        source_device_ids,
    )
    return {row["device_id"]: row for row in c.fetchall()}


def calculate_fcu_temperatures10x(
    conn, fcu_device_ids: list[int]
) -> dict[int, int]:
    weights_by_fcu = _fcu_temp_source_weights_for_fcus(conn, fcu_device_ids)
    source_device_ids = sorted(
        {
            source_device_id
            for weights in weights_by_fcu.values()
            for source_device_id, multiplier in weights.items()
            if multiplier > 0
        }
    )
    source_rows = _latest_temperature_rows_by_source(conn, source_device_ids)
    now = int(time.time())

    calculated: dict[int, int] = {}
    for fcu_device_id, weights in weights_by_fcu.items():
        weighted_total = 0.0
        weight_total = 0.0
        for source_device_id, multiplier in weights.items():
            if multiplier <= 0:
                continue
            temp_row = source_rows.get(source_device_id)
            if temp_row is None:
                continue
            last_valid = temp_row["logtime"] + temp_row["duration"]
            if now - last_valid > TEMP_SOURCE_STALE_SECONDS:
                continue
            weighted_total += temp_row["temp10x"] * multiplier
            weight_total += multiplier
        if weight_total > 0:
            calculated[fcu_device_id] = int(
                math.floor((weighted_total / weight_total) + 0.5)
            )
    return calculated


def _fcu_self_source_multipliers(
    conn,
    fcu_device_ids: list[int],
) -> dict[int, float]:
    if not fcu_device_ids:
        return {}
    wanted_values = ",".join(["(?)"] * len(fcu_device_ids))
    c = conn.cursor()
    c.execute(
        f"""
        WITH wanted(fcu_device_id) AS (VALUES {wanted_values})
        SELECT s.fcu_device_id, s.multiplier
        FROM fcu_temp_sources s
        JOIN wanted w ON s.fcu_device_id = w.fcu_device_id
        WHERE s.source_device_id = s.fcu_device_id
        """,
        fcu_device_ids,
    )
    return {row["fcu_device_id"]: float(row["multiplier"]) for row in c.fetchall()}


def _temperature_rows_by_source_for_window(
    conn, source_device_ids: list[int], start_logtime: int, end_logtime: int
) -> dict[int, list[sqlite3.Row]]:
    rows_by_source: dict[int, list[sqlite3.Row]] = {
        source_device_id: [] for source_device_id in source_device_ids
    }
    if not source_device_ids:
        return rows_by_source

    wanted_values = ",".join(["(?)"] * len(source_device_ids))
    c = conn.cursor()
    c.execute(
        f"""
        WITH wanted(device_id) AS (VALUES {wanted_values}),
        prior AS (
            SELECT d.device_id, MAX(d.logtime) AS logtime
            FROM devlog d
            JOIN wanted w ON d.device_id = w.device_id
            WHERE d.temp10x IS NOT NULL AND d.logtime <= ?
            GROUP BY d.device_id
        )
        SELECT d.device_id, d.logtime, d.duration, d.temp10x
        FROM devlog d
        JOIN wanted w ON d.device_id = w.device_id
        LEFT JOIN prior p ON d.device_id = p.device_id
        WHERE d.temp10x IS NOT NULL
            AND d.logtime <= ?
            AND (d.logtime >= ? OR d.logtime = p.logtime)
        ORDER BY d.device_id, d.logtime
        """,
        [*source_device_ids, start_logtime, end_logtime, start_logtime],
    )
    for row in c.fetchall():
        rows_by_source[row["device_id"]].append(row)
    return rows_by_source


def _calculate_fcu_temperature10x_from_prefetched_rows(
    weights: dict[int, float],
    rows_by_source: dict[int, list[sqlite3.Row]],
    row_indexes: dict[int, int],
    at_time: int,
) -> int | None:
    weighted_total = 0.0
    weight_total = 0.0
    for source_device_id, multiplier in weights.items():
        rows = rows_by_source.get(source_device_id, [])
        row_index = row_indexes.get(source_device_id, -1)
        while (
            row_index + 1 < len(rows)
            and rows[row_index + 1]["logtime"] <= at_time
        ):
            row_index += 1
        row_indexes[source_device_id] = row_index
        if row_index < 0:
            continue

        temp_row = rows[row_index]
        last_valid = temp_row["logtime"] + temp_row["duration"]
        if at_time - last_valid > TEMP_SOURCE_STALE_SECONDS:
            continue
        weighted_total += temp_row["temp10x"] * multiplier
        weight_total += multiplier

    if weight_total <= 0:
        return None
    return int(math.floor((weighted_total / weight_total) + 0.5))


def _set_fcu_temp_source_multiplier(
    conn,
    *,
    fcu_device_id: int,
    source_device_id: int,
    multiplier: float,
    ipaddr: str | None,
    agent: str | None,
):
    c = conn.cursor()
    fcu = get_device(conn, fcu_device_id)
    source = get_device(conn, source_device_id)
    if fcu is None:
        raise ValueError(f"Unknown fcu_device_id: {fcu_device_id}")
    if source is None:
        raise ValueError(f"Unknown source_device_id: {source_device_id}")

    c.execute(
        """
        SELECT multiplier
        FROM fcu_temp_sources
        WHERE fcu_device_id=? AND source_device_id=?
        """,
        (fcu_device_id, source_device_id),
    )
    row = c.fetchone()
    old_multiplier = (
        float(row["multiplier"])
        if row
        else get_fcu_temp_source_weights(conn, fcu_device_id).get(source_device_id, 0.0)
    )
    new_multiplier = float(multiplier)
    if old_multiplier == new_multiplier:
        return

    now = int(time.time())
    c.execute(
        """
        INSERT INTO fcu_temp_sources
            (fcu_device_id, source_device_id, multiplier, updated_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(fcu_device_id, source_device_id)
        DO UPDATE SET multiplier=excluded.multiplier, updated_at=excluded.updated_at
        """,
        (fcu_device_id, source_device_id, new_multiplier, now),
    )

    insert_changelog(
        conn,
        ipaddr=ipaddr or "",
        device_id=fcu_device_id,
        ae200_device_id=fcu.get("ae200_device_id"),
        current_values=str(old_multiplier),
        new_value=str(new_multiplier),
        agent=agent or "",
        comment=(
            "calculated temp multiplier for source "
            f"{source_device_id} ({source['device_name']})"
        ),
        commit=False,
    )


def set_fcu_temp_source_multiplier(
    conn,
    *,
    fcu_device_id: int,
    source_device_id: int,
    multiplier: float,
    ipaddr: str | None,
    agent: str | None,
) -> dict[str, Any]:
    try:
        _set_fcu_temp_source_multiplier(
            conn,
            fcu_device_id=fcu_device_id,
            source_device_id=source_device_id,
            multiplier=multiplier,
            ipaddr=ipaddr,
            agent=agent,
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return get_fcu_temp_sources(conn, fcu_device_id)


def set_fcu_temp_source_multipliers(
    conn,
    *,
    updates: list[FcuTempSourceControl],
    ipaddr: str | None,
    agent: str | None,
) -> dict[str, Any]:
    if not updates:
        raise ValueError("At least one temperature source update is required")
    fcu_device_id = updates[0].fcu_device_id
    try:
        for update in updates:
            if update.fcu_device_id != fcu_device_id:
                raise ValueError("All updates must use the same fcu_device_id")
            _set_fcu_temp_source_multiplier(
                conn,
                fcu_device_id=update.fcu_device_id,
                source_device_id=update.source_device_id,
                multiplier=update.multiplier,
                ipaddr=ipaddr,
                agent=agent,
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return get_fcu_temp_sources(conn, fcu_device_id)


def _fcu_devices_from_current_status(conn) -> list[dict[str, Any]]:
    devices = fetch_last_status_fixed(conn)
    fcus: list[dict[str, Any]] = []
    for device in devices:
        if "status" in device:
            device.update(ae200.extract_drive_and_fan_speed(device["status"]))
        if is_fcu_device(device):
            fcus.append(device)
    return fcus


def get_calculated_temperature_series(
    conn, device_ids: List[int] | None = None
) -> List[Dict[str, Any]]:
    fcus = _fcu_devices_from_current_status(conn)
    if device_ids:
        wanted = set(device_ids)
        fcus = [fcu for fcu in fcus if fcu["device_id"] in wanted]

    c = conn.cursor()
    series: list[TimeSeries] = []
    for fcu in fcus:
        cmd = """
        SELECT logtime
        FROM devlog
        WHERE device_id=? AND logtime IS NOT NULL AND temp10x IS NOT NULL
        """
        args = [fcu["device_id"]]
        (cmd, args) = temporal_quantification(cmd, args)
        cmd += " ORDER BY logtime "
        c.execute(cmd, args)
        logtime_rows = c.fetchall()
        if not logtime_rows:
            continue

        weights = {
            source_device_id: multiplier
            for source_device_id, multiplier in get_fcu_temp_source_weights(
                conn, fcu["device_id"]
            ).items()
            if multiplier > 0
        }
        if not weights:
            continue

        source_rows = _temperature_rows_by_source_for_window(
            conn,
            list(weights.keys()),
            _chart_logtime(logtime_rows[0]),
            _chart_logtime(logtime_rows[-1]),
        )
        row_indexes = {source_device_id: -1 for source_device_id in weights}

        data = []
        for row in logtime_rows:
            logtime = _chart_logtime(row)
            temp10x = _calculate_fcu_temperature10x_from_prefetched_rows(
                weights, source_rows, row_indexes, logtime
            )
            if temp10x is not None:
                data.append((logtime, temp10x / 10))
        if data:
            series.append(
                TimeSeries(
                    device_id=fcu["device_id"],
                    name=fcu.get("display_name") or fcu["device_name"],
                    data=data,
                )
            )
    return json_ready_list(series)


def get_temperature_series(
    conn, device_ids: List[int] | None = None
) -> List[Dict[str, Any]]:
    """Get temperature series data for devices.
    :param device_ids: a list of integer device IDs or None. An empty list or None gets all devices
    :return: a list of dicts each with device_id, name (raw device_name), and data: [[time1,val1], ...]
    """
    c = conn.cursor()
    # Get all devices
    c.execute("SELECT * from devices")
    devices = c.fetchall()
    if not device_ids:
        device_ids = [dev["device_id"] for dev in devices]

    series: list[TimeSeries] = []
    for dev in devices:
        if dev["device_id"] in device_ids:
            cmd = """
            SELECT logtime,temp10x from devlog
            WHERE device_id=? AND logtime IS NOT NULL AND temp10x IS NOT NULL
            """
            args = [dev["device_id"]]
            (cmd, args) = temporal_quantification(cmd, args)
            cmd += " ORDER BY logtime "
            c.execute(cmd, args)
            rows = c.fetchall()
            data = [(_chart_logtime(row), row["temp10x"] / 10) for row in rows]
            if data:
                series.append(
                    TimeSeries(
                        device_id=dev["device_id"],
                        name=dev["display_name"] or dev["device_name"],
                        data=data,
                    )
                )
    return json_ready_list(series)


def get_device_metric_series(
    conn, status_key: str, device_ids: List[int] | None = None
) -> List[Dict[str, Any]]:
    """Get a per-device time series for an arbitrary status_json metric.

    Mirrors get_lighting_series but parameterized on the status_json key.
    Values may be scalars or ``{value, unit}`` dicts; see
    ``aq_metrics.extract_metric_from_status``.
    """
    c = conn.cursor()
    c.execute("SELECT device_id, device_name, display_name FROM devices")
    devices = c.fetchall()

    if not device_ids:
        device_ids = [dev["device_id"] for dev in devices]

    series: list[TimeSeries] = []

    for dev in devices:
        device_id = dev["device_id"]
        if device_id not in device_ids:
            continue

        cmd = """
            SELECT logtime, status_json
            FROM devlog
            WHERE device_id = ? AND logtime IS NOT NULL AND status_json IS NOT NULL
            """
        args = [device_id]
        (cmd, args) = temporal_quantification(cmd, args)
        cmd += " ORDER BY logtime"
        c.execute(cmd, args)
        rows = c.fetchall()

        data: list[tuple[int, float]] = []
        for row in rows:
            try:
                status = json.loads(row["status_json"])
            except (TypeError, json.JSONDecodeError):
                continue
            val = extract_metric_from_status(status, status_key)
            if val is None:
                continue
            data.append((_chart_logtime(row), val))

        if data:
            series.append(
                TimeSeries(
                    name=dev["display_name"] or dev["device_name"],
                    device_id=device_id,
                    data=data,
                )
            )

    return json_ready_list(series)


def get_lighting_series(
    conn, device_ids: List[int] | None = None
) -> List[Dict[str, Any]]:
    """Get lighting (illuminance) series data for devices.

    Values are taken from ``devlog.status_json`` where available, using the
    top-level ``illuminance`` field first and falling back to
    ``attributes.illuminance`` when present.
    """
    c = conn.cursor()
    c.execute("SELECT device_id, device_name, display_name FROM devices")
    devices = c.fetchall()

    if not device_ids:
        device_ids = [dev["device_id"] for dev in devices]

    series: list[TimeSeries] = []

    for dev in devices:
        device_id = dev["device_id"]
        if device_id not in device_ids:
            continue

        cmd = """
            SELECT logtime, status_json
            FROM devlog
            WHERE device_id = ? AND logtime IS NOT NULL AND status_json IS NOT NULL
            """
        args = [device_id]
        (cmd, args) = temporal_quantification(cmd, args)
        cmd += " ORDER BY logtime"
        c.execute(cmd, args)
        rows = c.fetchall()

        data: list[tuple[int, float]] = []
        for row in rows:
            status_json = row["status_json"]
            try:
                status = json.loads(status_json)
            except (TypeError, json.JSONDecodeError):
                continue

            illum = status.get("illuminance")
            if illum is None:
                attrs = status.get("attributes") or {}
                illum = attrs.get("illuminance")
            if illum is None:
                light = status.get("light")
                if isinstance(light, dict):
                    illum = light.get("value")

            try:
                if illum is None or illum == "":
                    continue
                illum_val = float(illum)
            except (TypeError, ValueError):
                continue

            data.append((_chart_logtime(row), illum_val))

        if data:
            series.append(
                TimeSeries(
                    name=dev["display_name"] or dev["device_name"],
                    device_id=device_id,
                    data=data,
                )
            )

    return json_ready_list(series)


def get_device_status(conn) -> List[Dict[str, Any]]:
    """Get device status with annotations"""
    device_data = fetch_last_status_fixed(conn)
    fcu_device_ids = []

    # Extract and convert the top-level drive, speed, and other items
    for data in device_data:
        data["rules_enabled"] = bool(data.get("rules_enabled", True))
        if "status" in data:
            data.update(ae200.extract_drive_and_fan_speed(data["status"]))
            status = data["status"]
            illum = status.get("illuminance")
            if illum is None:
                illum = (status.get("attributes") or {}).get("illuminance")
            data["has_illuminance"] = illum is not None
            for metric_name, status_key in AQ_METRIC_STATUS_KEYS.items():
                data[f"has_{metric_name}"] = (
                    extract_metric_from_status(status, status_key) is not None
                )
            if is_fcu_device(data):
                data["temp_source_stale_seconds"] = TEMP_SOURCE_STALE_SECONDS
                fcu_device_ids.append(data["device_id"])
        inferred_type = infer_device_type(data)
        if inferred_type:
            data["device_type"] = inferred_type

    set_ranges = get_fcu_set_ranges(conn, fcu_device_ids)
    calculated_temps = calculate_fcu_temperatures10x(conn, fcu_device_ids)
    fcu_self_multipliers = _fcu_self_source_multipliers(conn, fcu_device_ids)
    for data in device_data:
        if data["device_id"] in fcu_device_ids:
            set_range = set_ranges.get(data["device_id"]) or default_fcu_set_range(
                data["device_id"],
                _set_temp_c_from_status(data.get("status")),
            )
            data["set_range_low_c"] = set_range.set_range_low_c
            data["set_range_high_c"] = set_range.set_range_high_c
            data["min_set_range_c"] = set_range.min_set_range_c
        calculated_temp10x = calculated_temps.get(data["device_id"])
        if (
            calculated_temp10x is None
            and data["device_id"] in fcu_device_ids
            and data.get("temp10x") is not None
            and fcu_self_multipliers.get(
                data["device_id"],
                FCU_DEFAULT_TEMP_SOURCE_MULTIPLIER,
            )
            > 0
        ):
            calculated_temp10x = data["temp10x"]
        if calculated_temp10x is not None:
            data["calculated_temp10x"] = calculated_temp10x
        if "logtime" in data:
            data["logtime"] = int(data["logtime"])
            if data.get("duration") is not None:
                data["duration"] = int(data["duration"])
            data["age"] = github_style_duration(
                data["logtime"] + data.get("duration", 1)
            )

    return [json_ready(DeviceStatus.model_validate(data)) for data in device_data]


def get_changelog(
    conn,
    draw: int = 1,
    start_row: int | None = 0,
    length: int | None = 100,
) -> Dict[str, Any]:
    """Get changelog data with pagination.

    Temporal bounds (start/end) are taken directly from the current request
    via :func:`temporal_quantification`.
    """
    cmd = """SELECT c.logtime, c.ipaddr, d.device_name as unit, c.current_values, c.new_value, c.agent, c.comment FROM changelog c
               LEFT JOIN devices d ON c.device_id = d.device_id WHERE 1=1"""
    args: List[Any] = []

    (cmd, args) = temporal_quantification(cmd, args)

    if length is None:
        length = 100
    if start_row is None:
        start_row = 0

    cmd += " ORDER BY logtime DESC LIMIT ? OFFSET ?"
    args.extend([length, start_row])

    logger.debug("cmd=%s args=%s", cmd, args)

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

    return json_ready(
        ChangelogResponse.model_validate(
            {
                "draw": draw,
                "recordsTotal": len(rows),
                "recordsFiltered": len(rows),  # Adjust if implementing search
                "data": [ChangelogRow.model_validate(row) for row in rows],
            }
        )
    )


def get_device_log(conn, device_id: int) -> Dict[str, Any]:
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

    return {"device": device, "devlog": devlog, "changelog": changelog}


def insert_into_aqi(conn, values):
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO aqi (logtime,aqi,co,h,no2,o3,p,pm10,pm25,so2,t,w) values (:logtime,:aqi,:co,:h,:no2,:o3,:p,:pm10,:pm25,:so2,:t,:w)",
        values,
    )
    conn.commit()


def get_db_aqi(conn) -> Dict[str, Any]:
    """
    Get AQI from database.

    :param conn: database connection
    :return: AQI data dict with value, color, name
    """
    # Check for recent AQI data in database
    c = conn.cursor()
    c.execute("SELECT aqi FROM aqi order by logtime DESC limit 1")
    row = c.fetchone()
    aqi = row[0] if row is not None else 0
    return json_ready(AqiSummary.model_validate(airquality.aqi_decode(aqi)))


def get_aqi_and_weather_data(conn) -> Dict[str, Any]:
    """Get combined weather and AQI data"""
    aqi_data = get_db_aqi(conn)
    weather_data = weather.get_weather_data()
    return json_ready(
        AqiWeatherResponse.model_validate({"aqi": aqi_data, "weather": weather_data})
    )

def get_all_device_aqi(conn) -> List[Dict[str, Any]]:
    """
    :return: list of dicts where each has device_id, device_name, and status;
             status["aqi"] is a dict of AQI values (same structure as get_db_aqi())
    """
    statuses = fetch_last_status_fixed(conn, flag=AIR_MON_DEVICES)
    statuses.append({"device_id": 0, "device_name": "Outdoor Air Quality", "status": {"aqi": get_db_aqi(conn)}})
    return [json_ready(DeviceStatus.model_validate(status)) for status in statuses]
