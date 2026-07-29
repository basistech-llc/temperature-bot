"""Contract tests for the dashboard view models.

These models exist because Jinja fails silently: an attribute the template asks
for and the route never supplied renders as the empty string, so a lost label
looks like a design choice rather than a bug. The tests below pin the two
mechanisms that turn such a mistake into a loud failure.
"""

import time

import pytest
from pydantic import ValidationError

from app.aq_metrics import AQ_METRIC_STATUS_KEYS
from app.dashboard_views import (
    DashboardDeviceView,
    annotate_device_rows,
    build_dashboard_page,
)
from app.models import Room


def _raw_row(**overrides):
    """A status row shaped like db.get_device_status() output."""
    row = {
        "device_id": 1,
        "device_name": "Broadway South",
        "logtime": 1785318000,
        "duration": 60,
        "temp10x": 231,
    }
    row.update(overrides)
    return row


def test_has_flags_cover_every_air_quality_metric():
    """Adding a metric must not silently skip the dashboard.

    db.get_device_status() derives one has_<metric> key per
    AQ_METRIC_STATUS_KEYS entry. Those keys are declared statically on the view
    model, so a new metric would otherwise be rejected by extra="forbid" at
    render time -- or, worse, quietly missing from the sensor matrix. This test
    fails at the moment the two lists diverge.
    """
    field_names = dict(DashboardDeviceView.model_fields).keys()
    declared = {
        name[len("has_") :] for name in field_names if name.startswith("has_")
    }
    # has_illuminance and has_speed_control are derived separately, not from
    # the air-quality metric table.
    declared -= {"illuminance", "speed_control"}

    assert declared == set(AQ_METRIC_STATUS_KEYS)


def test_unknown_key_is_rejected():
    """A key the database starts emitting must fail loudly, not vanish.

    With extra="allow" a new derived key would flow into the template
    unnoticed, and a typo in one would render as blank. extra="forbid" turns
    both into an error at build time.
    """
    row = _raw_row(
        device_label="x",
        device_label_with_icon="x",
        device_update_text="",
        device_update_tooltip="x",
        newly_derived_key=1,
    )
    with pytest.raises(ValidationError, match="newly_derived_key"):
        DashboardDeviceView.model_validate(row)


def test_display_fields_are_required():
    """A route that forgets a display field must fail, not render a blank cell.

    index.html renders these unconditionally, so defaulting them to "" would
    reproduce exactly the silent-blank failure these models exist to prevent.
    """
    with pytest.raises(ValidationError) as excinfo:
        DashboardDeviceView.model_validate(_raw_row())

    missing = {error["loc"][0] for error in excinfo.value.errors()}
    assert missing == {
        "device_label",
        "device_label_with_icon",
        "device_update_text",
        "device_update_tooltip",
    }


def test_annotate_then_validate_accepts_a_sparse_row():
    """A row with no status_json must still build.

    Rows without a devlog status carry none of the has_* flags or AE-200
    extracts, so every one of those fields has to be optional. This is the case
    that would 500 the whole dashboard if a field were wrongly made required.
    """
    rows = [_raw_row(status=None)]
    annotate_device_rows(rows, int(time.time()))
    view = DashboardDeviceView.model_validate(rows[0])

    assert view.has_co2 is False
    assert view.drive is None
    assert view.device_label == "Broadway South"


def test_build_dashboard_page_groups_and_summarizes():
    """The page model assembles the whole template contract in one call."""
    now = 1785318000
    rows = [
        _raw_row(device_id=1, device_name="Hickory FCU", device_type="FCU", room_id=1),
        _raw_row(device_id=2, device_name="Hickory Sensor", device_type="SENSOR", room_id=1),
    ]
    page = build_dashboard_page(
        rows, [Room(room_id=1, room_name="Hickory")], set(), now=now
    )

    assert page.now == now
    assert [device.device_name for device in page.devices] == [
        "Hickory FCU",
        "Hickory Sensor",
    ]
    assert [group.room_name for group in page.room_groups] == ["Hickory", "Unassigned"]
    hickory = page.room_groups[0]
    assert [device.device_name for device in hickory.devices] == ["Hickory Sensor"]
    assert page.table_update_summaries["fcu"] is not None
