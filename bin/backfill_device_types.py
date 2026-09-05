"""Classify devices whose database type is currently null."""

import argparse
import json
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from app import db, hubitat  # noqa: E402
from app.constants import RESERVED_DEVICE_NAMES  # noqa: E402
from app.device_types import (  # noqa: E402
    DEVICE_TYPE_INTERNAL,
    DEVICE_TYPE_SENSOR,
    HubitatDevice,
    classify_hubitat_device,
    classify_legacy_hubitat_name,
)


def _hubitat_inventory() -> dict[str, HubitatDevice]:
    return {
        device.name: device
        for device in (
            HubitatDevice.model_validate(item) for item in hubitat.get_all_devices()
        )
    }


def _latest_status(conn, device_id: int) -> HubitatDevice | None:
    rows = conn.execute(
        """
        SELECT status_json FROM devlog
        WHERE device_id=? AND status_json LIKE '%"capabilities"%'
        ORDER BY logtime DESC
        """,
        (device_id,),
    ).fetchall()
    for row in rows:
        try:
            payload = json.loads(row["status_json"])
            if isinstance(payload, dict) and "capabilities" in payload:
                return HubitatDevice.model_validate(payload)
        except (json.JSONDecodeError, ValueError):
            continue
    return None


def _classify_row(conn, row, live) -> tuple[int, str, str | None, str]:
    """Classify one row without consulting its stored device_type."""
    name = row["device_name"]
    if row["ae200_device_id"] is not None:
        device_type = "ERV" if name.lower().startswith("erv") else "FCU"
        evidence = "AE-200 device mapping"
    elif name.startswith("Airthings "):
        device_type, evidence = DEVICE_TYPE_SENSOR, "Airthings collector identity"
    elif name in RESERVED_DEVICE_NAMES:
        device_type, evidence = DEVICE_TYPE_INTERNAL, "reserved internal device name"
    else:
        device = live.get(name) or _latest_status(conn, row["device_id"])
        if device:
            device_type, evidence = classify_hubitat_device(device)
        else:
            device_type, evidence = classify_legacy_hubitat_name(name)
    return row["device_id"], name, device_type, evidence


def infer_device_types(conn, *, all_devices: bool = False):
    """Classify pending rows, or every row when requested."""
    condition = "" if all_devices else "WHERE device_type IS NULL OR trim(device_type)='' OR device_type='OTHER'"
    rows = conn.execute(
        f"""
        SELECT device_id, device_name, ae200_device_id FROM devices
        {condition}
        ORDER BY device_name
        """
    ).fetchall()
    live = _hubitat_inventory()
    return [_classify_row(conn, row, live) for row in rows]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("database")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--all", action="store_true", help="report every device")
    args = parser.parse_args()
    conn = db.connect_db(args.database)
    results = infer_device_types(conn, all_devices=args.all)
    if args.apply:
        conn.executemany(
            """
            UPDATE devices SET device_type=?
            WHERE device_id=? AND (
                device_type IS NULL OR trim(device_type)='' OR device_type='OTHER'
            )
            """,
            ((device_type, device_id) for device_id, _name, device_type, _why in results if device_type),
        )
        conn.commit()
    print("DEVICE_ID\tNAME\tINFERRED_TYPE\tEVIDENCE")
    for device_id, name, device_type, evidence in results:
        print(f"{device_id}\t{name}\t{device_type or 'UNKNOWN'}\t{evidence}")
    return 0 if all(item[2] for item in results) else 2


if __name__ == "__main__":
    raise SystemExit(main())
