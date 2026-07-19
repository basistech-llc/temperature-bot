"""
ae200 controller.
Originally from https://github.com/natevoci/ae200.
Includes both async routines and synchronous covers.

Simulator if AE200_SIMULATOR contains an explicit true value

"""

# pylint: disable=invalid-name
# pylint: disable=line-too-long
# pylint: disable=missing-function-docstring
# pylint: disable=redefined-outer-name

import contextlib
import fcntl
import os
from os.path import dirname,join
from pathlib import Path
import asyncio
import xml.etree.ElementTree as ET
import logging
import json
import threading
import time

import concurrent.futures
import websockets
from websockets.extensions import permessage_deflate
from websockets.typing import Origin, Subprotocol

from app.util import env_flag_enabled, get_config
from app import ae200_command_log, performance_monitoring

logger = logging.getLogger(__name__)
B_XMLPROC_SUBPROTOCOL = Subprotocol("b_xmlproc")


class AE200VerificationError(RuntimeError):
    """The controller read-back did not match a completed write request."""


# Fan mapping speeds. Note that there is no 'OFF'
FAN_SPEED_AUTO = -1
DRIVES = {0:"OFF", 1:"ON"}
FAN_SPEEDS = {-1:"AUTO", 1: "LOW", 2: "MID2", 3: "MID1", 4: "HIGH"}
FAN_SPEED_NAMES = {value: key for key, value in FAN_SPEEDS.items()}
DRIVE_NAMES = {value: key for key, value in DRIVES.items()}
AE200_DRIVE_KEY = "Drive"
AE200_FAN_SPEED_KEY = "FanSpeed"
AE200_MODE_KEY = "Mode"
AE200_SET_TEMP_KEY = "SetTemp"
AE200_COOL_SET_TEMP_KEY = "SetTemp1"
AE200_HEAT_SET_TEMP_KEY = "SetTemp2"
AE200_AUTO_MIN_KEY = "AutoMin"
AE200_AUTO_MAX_KEY = "AutoMax"
AE200_ALLOWED_SET_MODES = frozenset({"FAN", "COOL", "DRY", "HEAT", "AUTO"})
AE200_GROUP_KEY = "Group"
ERROR_SIGN = "ErrorSign"
FILTER_SIGN = "FilterSign"
CHECK_WATER = "CheckWater"
ALERT_FIELDS = (ERROR_SIGN, FILTER_SIGN, CHECK_WATER)
ALERT_LABELS = {
    ERROR_SIGN: "error condition",
    FILTER_SIGN: "filter warning",
    CHECK_WATER: "water issue",
}
AE200_COMMAND_LOCK_PATH = os.getenv("AE200_COMMAND_LOCK_PATH", "/tmp/temperature-bot-ae200.lock")
AE200_WRITE_SETTLE_SECONDS = float(os.getenv("AE200_WRITE_SETTLE_SECONDS", "0.25"))

# User-facing fan-speed labels, keyed by speed number. These intentionally
# mirror the speed-button text rendered in room_dashboard.html / index.html so
# every surface speaks the same vocabulary (the room dashboard reads its labels
# straight off those buttons; surfaces without buttons — e.g. the alerts table —
# use the maps below). ERVs and plain fans expose different levels, so the label
# for a given speed number depends on device type. Keep these in sync with the
# template button text if either changes.
_ERV_SPEED_LABELS = {-1: "Auto", 1: "LO", 2: "MED-LO", 3: "MED-HI", 4: "HI"}
_FAN_SPEED_LABELS = {-1: "Auto", 2: "LO", 3: "MED", 4: "HI"}


def friendly_fan_speed_label(device_name, raw_fan_speed):
    """Return a user-facing fan-speed label (e.g. 'HI', 'MED-LO', 'Auto').

    :param device_name: device name; ERVs (name starts with 'ERV') use a
        different label set than plain fans.
    :param raw_fan_speed: either the protocol string ('HIGH', 'MID1', ...) or
        the speed number. Anything unrecognized is returned unchanged so we
        never hide diagnostic data behind a guess.
    """
    if raw_fan_speed is None:
        return None
    # Normalize to a speed number, accepting either protocol string or int.
    if isinstance(raw_fan_speed, str):
        speed = FAN_SPEED_NAMES.get(raw_fan_speed)
    else:
        speed = raw_fan_speed
    if speed is None:
        return str(raw_fan_speed)
    is_erv = (device_name or "").upper().startswith("ERV")
    labels = _ERV_SPEED_LABELS if is_erv else _FAN_SPEED_LABELS
    return labels.get(speed, str(raw_fan_speed))

AE200_SIMULATOR_ENV = "AE200_SIMULATOR"


def ae200_simulator_enabled() -> bool:
    """Return True when AE-200 simulator mode is explicitly enabled."""
    return env_flag_enabled(AE200_SIMULATOR_ENV)


AE200_SIMULATOR = ae200_simulator_enabled()
SIMULATOR_DIR = Path(join(dirname(__file__), "test_data"))

getUnitsPayload = """<?xml version="1.0" encoding="UTF-8" ?>
<Packet>
<Command>getRequest</Command>
<DatabaseManager>
<ControlGroup>
<MnetList />
</ControlGroup>
</DatabaseManager>
</Packet>
"""

setRequestPayload = """<?xml version="1.0" encoding="UTF-8" ?>
<Packet>
<Command>setRequest</Command>
<DatabaseManager>
<Mnet Group="{deviceId}" {attrs}  />
</DatabaseManager>
</Packet>
"""


def getMnetDetails(deviceIds):
    mnets = "\n".join(
        [
            f'<Mnet Group="{deviceId}" Drive="*" Vent24h="*" Mode="*" VentMode="*" ModeStatus="*" SetTemp="*" SetTemp1="*" SetTemp2="*" SetTemp3="*" SetTemp4="*" SetTemp5="*" SetHumidity="*" InletTemp="*" InletHumidity="*" AirDirection="*" FanSpeed="*" RemoCon="*" DriveItem="*" ModeItem="*" SetTempItem="*" FilterItem="*" AirDirItem="*" FanSpeedItem="*" TimerItem="*" CheckWaterItem="*" FilterSign="*" Hold="*" EnergyControl="*" EnergyControlIC="*" SetbackControl="*" Ventilation="*" VentiDrive="*" VentiFan="*" Schedule="*" ScheduleAvail="*" ErrorSign="*" CheckWater="*" TempLimitCool="*" TempLimitHeat="*" TempLimit="*" CoolMin="*" CoolMax="*" HeatMin="*" HeatMax="*" AutoMin="*" AutoMax="*" TurnOff="*" MaxSaveValue="*" RoomHumidity="*" Brightness="*" Occupancy="*" NightPurge="*" Humid="*" Vent24hMode="*" SnowFanMode="*" InletTempHWHP="*" OutletTempHWHP="*" HeadTempHWHP="*" OutdoorTemp="*" BrineTemp="*" HeadInletTempCH="*" BACnetTurnOff="*" AISmartStart="*"  />'
            for deviceId in deviceIds
        ]
    )
    return f"""<?xml version="1.0" encoding="UTF-8" ?>
<Packet>
<Command>getRequest</Command>
<DatabaseManager>
{mnets}
</DatabaseManager>
</Packet>
"""


################################################################
### support functions
def cleanDeviceInfo(statusdict):
    """Given the statusdict, remove empty values"""
    return {key:value for (key,value) in statusdict.items() if value!=""}

def int_to_drive(drive):
    if str(drive).upper() in ["1","TRUE","ON","YES"]:
        return "ON"
    else:
        return "OFF"


def extract_drive_and_fan_speed(data):
    """Return normalized AE-200 control fields for app JSON responses."""
    ret = {}
    mode = data.get(AE200_MODE_KEY, None)
    if mode is not None:
        ret["mode"] = mode
    drive = data.get(AE200_DRIVE_KEY, None)
    speed = data.get(AE200_FAN_SPEED_KEY, None)
    if drive is None or speed is None:
        ret["has_speed_control"] = False
        return ret
    ret.update({
        "drive": DRIVE_NAMES[drive],
        "fan_speed": FAN_SPEED_NAMES[speed],
        "has_speed_control": True,
    })
    return ret


def _float_or_none(value):
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def extract_set_temperatures(data):
    """Return promoted AE-200 set-temperature fields for app JSON responses."""
    ret = {}
    field_map = {
        "set_temp_c": AE200_SET_TEMP_KEY,
        "cool_set_temp_c": AE200_COOL_SET_TEMP_KEY,
        "heat_set_temp_c": AE200_HEAT_SET_TEMP_KEY,
        "auto_min_c": AE200_AUTO_MIN_KEY,
        "auto_max_c": AE200_AUTO_MAX_KEY,
    }
    for response_key, status_key in field_map.items():
        value = _float_or_none(data.get(status_key))
        if value is not None:
            ret[response_key] = value
    return ret


def get_device_fan_speed(device):
    """Returns the device fanspeed as a number"""
    info = get_device_info(device)
    return FAN_SPEED_NAMES[info["FanSpeed"]]


def get_device_drive(device):
    """Returns the device fanspeed as a number"""
    info = get_device_info(device)
    return DRIVE_NAMES[info["Drive"]]


def get_device_mode(device):
    """Returns the device operation mode."""
    info = get_device_info(device)
    return info.get(AE200_MODE_KEY)


class AsyncRunner:  # pylint: disable=too-few-public-methods
    """Manages async operations for the application"""

    def __init__(self):
        self._command_semaphore = threading.BoundedSemaphore(value=1)

    def run_async_safely(self, coro, *, sample=None):
        """Run an async coroutine safely, handling existing event loops"""
        started_ns = time.perf_counter_ns()
        try:
            with self._command_semaphore:
                with ae200_command_lock():
                    if sample is not None:
                        sample.lock_wait_ms = performance_monitoring.elapsed_ms(
                            started_ns
                        )
                    result = self._run_async_safely(coro)
            if sample is not None:
                sample.success = True
                sample.outcome = "ok"
            return result
        except Exception as error:
            coro.close()
            if sample is not None:
                sample.mark_error(error)
            raise
        finally:
            if sample is not None:
                sample.total_ms = performance_monitoring.elapsed_ms(started_ns)
                performance_monitoring.record_sample_best_effort(sample)

    @staticmethod
    def _run_async_safely(coro):
        """Run an async coroutine from sync code without reusing event loops."""
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(coro)

        # We're already in an event loop, so run the coroutine in a separate
        # thread with its own short-lived loop.
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(asyncio.run, coro)
            return future.result()


@contextlib.contextmanager
def ae200_command_lock():
    """Serialize AE-200 websocket commands across local processes."""
    lock_fd = os.open(AE200_COMMAND_LOCK_PATH, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(lock_fd, fcntl.LOCK_UN)
        os.close(lock_fd)


# Singleton instance
runner = AsyncRunner()


################################################################
### controller class
class AE200Functions:
    """ae200 implementation."""

    def __init__(self, address=None):
        self._json = None
        self._temp_list = []
        if address is None:
            address = get_config()["ae200"]["host"]
        self.address = address

    async def _exchange(self, payload, sample, *, receive):
        """Send one XML payload while timing WebSocket phases."""
        connect_started_ns = time.perf_counter_ns()
        async with websockets.connect(
            f"ws://{self.address}/b_xmlproc/",
            extensions=[permessage_deflate.ClientPerMessageDeflateFactory()],
            origin=Origin(f"http://{self.address}"),
            subprotocols=[B_XMLPROC_SUBPROTOCOL],
        ) as websocket:
            if sample is not None:
                sample.connect_ms = performance_monitoring.elapsed_ms(
                    connect_started_ns
                )
            response_started_ns = time.perf_counter_ns()
            await websocket.send(payload)
            response = await websocket.recv() if receive else None
            if sample is not None:
                sample.response_ms = performance_monitoring.elapsed_ms(
                    response_started_ns
                )
                if response is not None:
                    sample.response_bytes = len(
                        response.encode("utf-8")
                        if isinstance(response, str)
                        else response
                    )
            close_started_ns = time.perf_counter_ns()
            await websocket.close()
            if sample is not None:
                sample.close_ms = performance_monitoring.elapsed_ms(close_started_ns)
            return response

    async def getDevicesAsync(self, sample=None):
        if AE200_SIMULATOR:
            raise RuntimeError("AE200_SIMULATOR not compatible with AE200Functions")
        unitsResultStr = await self._exchange(
            getUnitsPayload, sample, receive=True
        )
        unitsResultXML = ET.fromstring(unitsResultStr)

        groupList = []
        for r in unitsResultXML.findall(
            "./DatabaseManager/ControlGroup/MnetList/MnetRecord"
        ):
            # print( ET.tostring(r) )
            groupList.append({"id": r.get("Group"), "name": r.get("GroupNameWeb")})
        return groupList

    def getDevices(self):
        sample = (
            None
            if AE200_SIMULATOR
            else performance_monitoring.new_ae200_sample(
                performance_monitoring.OPERATION_GET_DEVICES, self.address
            )
        )
        return runner.run_async_safely(
            self.getDevicesAsync(sample), sample=sample
        )

    async def getDeviceInfoAsync(self, deviceId, clean=True, sample=None):
        """:param deviceId: The numeric ID of the device to get
        :param clean: if True (default), then remove keys with empty values.
        """
        if AE200_SIMULATOR:
            raise RuntimeError("AE200_SIMULATOR not compatible with AE200Functions")
        getMnetDetailsPayload = getMnetDetails([deviceId])
        mnetDetailsResultStr = await self._exchange(
            getMnetDetailsPayload, sample, receive=True
        )
        mnetDetailsResultXML = ET.fromstring(mnetDetailsResultStr)

        # result = {}
        node = mnetDetailsResultXML.find("./DatabaseManager/Mnet")
        if node is None:
            raise ValueError(f"AE-200 response omitted Mnet data for device {deviceId}")
        return cleanDeviceInfo(node.attrib) if clean else node.attrib

    def getDeviceInfo(self, deviceId, clean=True):
        sample = (
            None
            if AE200_SIMULATOR
            else performance_monitoring.new_ae200_sample(
                performance_monitoring.OPERATION_GET_DEVICE_INFO,
                self.address,
                deviceId,
            )
        )
        return runner.run_async_safely(
            self.getDeviceInfoAsync(deviceId, clean=clean, sample=sample),
            sample=sample,
        )

    async def sendAsync(self, deviceId, attributes, sample=None):
        assert "PYTEST" not in os.environ
        if AE200_SIMULATOR:
            raise RuntimeError("AE200_SIMULATOR not compatible with AE200Functions")
        attrs = " ".join([f'{key}="{attributes[key]}"' for key in attributes])
        payload = setRequestPayload.format(deviceId=deviceId, attrs=attrs)
        response_xml = await self._exchange(payload, sample, receive=True)
        response_root = ET.fromstring(response_xml)
        command = response_root.findtext("./Command") or ""
        if command != "setResponse":
            raise AE200VerificationError(
                f"AE-200 returned {command or 'no command'} for setRequest"
            )
        node = response_root.find("./DatabaseManager/Mnet")
        response_attributes = cleanDeviceInfo(node.attrib) if node is not None else {}
        response_attributes.pop(AE200_GROUP_KEY, None)
        return ae200_command_log.AE200SetResponse(
            command=command, response_fields=response_attributes
        )

    def send(self, deviceId, attributes):
        sample = (
            None
            if AE200_SIMULATOR
            else performance_monitoring.new_ae200_sample(
                performance_monitoring.OPERATION_SET, self.address, deviceId
            )
        )
        return runner.run_async_safely(
            self.sendAsync(deviceId, attributes, sample=sample), sample=sample
        )


################################################################
## Everything after here works with the simulator
################################################################

simulated_devices = {}
DEVICES = "devices"
if AE200_SIMULATOR:
    logger.debug("SIMULATOR ENABLED")
    simulated_devices[DEVICES] = json.loads(
        (SIMULATOR_DIR / "ae200_get_devices.json").read_bytes()
    )
    for dev in simulated_devices[DEVICES]:
        did = dev["id"]
        simulated_devices[did] = json.loads(
            (SIMULATOR_DIR / f"ae200_get_device_{did}.json").read_bytes()
        )


def register_simulated_device(ae200_device, name, statusdict=None):
    """Register a local DB-backed virtual AE-200 simulator unit."""
    if not AE200_SIMULATOR:
        return
    did = str(ae200_device)
    if did not in {str(device["id"]) for device in simulated_devices[DEVICES]}:
        simulated_devices[DEVICES].append({"id": did, "name": name})
    status = dict(statusdict or {})
    status.setdefault(AE200_DRIVE_KEY, DRIVES[1])
    status.setdefault(AE200_FAN_SPEED_KEY, FAN_SPEEDS[FAN_SPEED_AUTO])
    status.setdefault(AE200_MODE_KEY, "FAN")
    simulated_devices[did] = status


def set_drive(ae200_device, drive_int):
    drive_str = int_to_drive(drive_int)
    logger.info("set_drive(%s,%s,%s)", ae200_device, drive_int, drive_str)

    _send_command(ae200_device, {AE200_DRIVE_KEY: drive_str})


def set_fan_speed(ae200_device, speed):
    fan_speed = FAN_SPEEDS[speed]
    logger.info("set_fan_speed(%s,%s)=%s", ae200_device, speed, fan_speed)
    _send_command(ae200_device, {AE200_FAN_SPEED_KEY: fan_speed})


def set_fcu_state(ae200_device, *, drive=None, fan_speed=None):
    """Send drive and fan speed in one AE-200 write request."""
    attributes = {}
    if drive is not None:
        attributes[AE200_DRIVE_KEY] = DRIVES[drive]
    if fan_speed is not None:
        attributes[AE200_FAN_SPEED_KEY] = FAN_SPEEDS[fan_speed]
    if not attributes:
        raise ValueError("drive or fan_speed is required")
    logger.info("set_fcu_state(%s,%s)", ae200_device, attributes)
    _send_command(ae200_device, attributes)


def get_device_info_after_write(device):
    """Read state after the configured AE-200 write-settling interval."""
    if not AE200_SIMULATOR:
        time.sleep(AE200_WRITE_SETTLE_SECONDS)
    return get_device_info(device)


def set_set_temp(ae200_device, set_temp_c):
    """Set the unit set temperature in Celsius."""
    logger.info("set_set_temp(%s,%s)", ae200_device, set_temp_c)
    # AE-200 expects SetTemp as a string (e.g. "21.0")
    _send_command(ae200_device, {AE200_SET_TEMP_KEY: str(set_temp_c)})


def set_auto_set_temps(ae200_device, *, heat_set_temp_c, cool_set_temp_c):
    """Set the Auto-mode Heat/Cool dual setpoints in Celsius."""
    logger.info(
        "set_auto_set_temps(%s, heat=%s, cool=%s)",
        ae200_device,
        heat_set_temp_c,
        cool_set_temp_c,
    )
    payload = {
        AE200_COOL_SET_TEMP_KEY: str(cool_set_temp_c),
        AE200_HEAT_SET_TEMP_KEY: str(heat_set_temp_c),
    }
    _send_command(ae200_device, payload)


def set_mode(ae200_device, mode):
    mode = str(mode).upper()
    if mode not in AE200_ALLOWED_SET_MODES:
        raise ValueError(f"Unsupported AE-200 mode: {mode}")
    logger.info("set_mode(%s,%s)", ae200_device, mode)
    _send_command(ae200_device, {AE200_MODE_KEY: mode})


def _send_command(ae200_device, attributes):
    """Send one write and record its high-level AE-200 response."""
    attributes = {str(key): str(value) for key, value in attributes.items()}
    record = ae200_command_log.new_record(ae200_device, attributes)
    try:
        if AE200_SIMULATOR:
            simulated_devices[str(ae200_device)].update(attributes)
            response = ae200_command_log.AE200SetResponse(
                command="simulated", response_fields=attributes
            )
        else:
            response = AE200Functions().send(ae200_device, attributes)
        ae200_command_log.mark_response(
            record, response, simulated=AE200_SIMULATOR
        )
        return response
    except Exception as error:
        ae200_command_log.mark_error(record, error)
        raise
    finally:
        ae200_command_log.record_best_effort(record)


def get_device_info(device):
    logger.info("get_device_info(%s)", device)
    if AE200_SIMULATOR:
        try:
            return simulated_devices[str(device)]
        except KeyError:
            print(
                "************************************************************************"
            )
            print(
                f"Simulated device requested: {device} options: {simulated_devices.keys()}"
            )
            raise

    d = AE200Functions()
    return d.getDeviceInfo(device)


def get_devices():
    logger.info("get_devices()")
    if AE200_SIMULATOR:
        return simulated_devices[DEVICES]
    d = AE200Functions()
    return d.getDevices()


################################################################
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Demo function",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--host", help="address of the AE200 controller")
    parser.add_argument(
        "--json", help="Full JSON dump of the device(s)", action="store_true"
    )
    parser.add_argument(
        "--level", help="Specify level 0-4. 0 is off", type=int, default=0
    )
    args = parser.parse_args()

    d = AE200Functions(args.host)

    # Test reading device list
    devs = get_devices()
    print(json.dumps(devs))

    for dev in devs:
        did = dev["id"]
        name = dev["name"]
        # print(did, json.dumps(d.getDeviceInfo(did), indent=4))
        data = get_device_info(did)
        print(did, name, "drive: ", data["Drive"], "fan speed: ", data["FanSpeed"])

    if args.json:
        for dev in args.devices:
            did = int(dev)
            data = get_device_info(did)
            print(json.dumps(data, indent=4, default=str))
