"""
ae200 controller.
Originally from https://github.com/natevoci/ae200.
Includes both async routines and synchronous covers.

Simulator if AE200_SIMULATOR is set

"""

# pylint: disable=invalid-name
# pylint: disable=line-too-long
# pylint: disable=missing-function-docstring
# pylint: disable=redefined-outer-name

import os
from os.path import dirname,join
from pathlib import Path
import asyncio
import xml.etree.ElementTree as ET
import logging
import json

import concurrent.futures
import websockets
from websockets.extensions import permessage_deflate

from app.util import get_config

logger = logging.getLogger(__name__)

# Fan mapping speeds. Note that there is no 'OFF'
FAN_SPEED_AUTO = -1
DRIVES = {0:"OFF", 1:"ON"}
FAN_SPEEDS = {-1:"AUTO", 1: "LOW", 2: "MID2", 3: "MID1", 4: "HIGH"}
FAN_SPEED_NAMES = {value: key for key, value in FAN_SPEEDS.items()}
DRIVE_NAMES = {value: key for key, value in DRIVES.items()}

AE200_SIMULATOR = os.getenv('AE200_SIMULATOR')
SIMULATOR_DIR = Path(join(dirname(__file__),"test_data"))

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
    """Return a dict with drive/speed/has_speed_control"""
    drive = data.get('Drive',None)
    speed = data.get('FanSpeed',None)
    if drive is None or speed is None:
        return {'has_speed_control':False}
    return {
        'drive': DRIVE_NAMES[drive],
        'fan_speed': FAN_SPEED_NAMES[speed],
        'has_speed_control': True
    }

def get_device_fan_speed(device):
    """Returns the device fanspeed as a number"""
    info = get_device_info(device)
    return FAN_SPEED_NAMES[info['FanSpeed']]

def get_device_drive(device):
    """Returns the device fanspeed as a number"""
    info = get_device_info(device)
    return DRIVE_NAMES[info['Drive']]

class AsyncRunner:
    """Manages async operations for the application"""

    def __init__(self):
        self._loop = None

    def get_loop(self):
        """Get or create the application's event loop"""
        if self._loop is None:
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
        return self._loop

    def run_async_safely(self, coro):
        """Run an async coroutine safely, handling existing event loops"""
        try:
            # Try to get the current running loop
            loop = asyncio.get_running_loop()
            # We're already in an event loop, so we need to run in a separate thread
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(asyncio.run, coro)
                return future.result()
        except RuntimeError:
            # No event loop running, use the app's event loop
            loop = self.get_loop()
            return loop.run_until_complete(coro)

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
            address = get_config()['ae200']['host']
        self.address = address

    async def getDevicesAsync(self):
        if AE200_SIMULATOR:
            raise RuntimeError("AE200_SIMULATOR not compatiable with AE200Functions")
        async with websockets.connect(
            f"ws://{self.address}/b_xmlproc/",
            extensions=[permessage_deflate.ClientPerMessageDeflateFactory()],
            origin=f"http://{self.address}",
            subprotocols=["b_xmlproc"] ) as websocket:
            await websocket.send(getUnitsPayload)
            unitsResultStr = await websocket.recv()
            unitsResultXML = ET.fromstring(unitsResultStr)

            groupList = []
            for r in unitsResultXML.findall( "./DatabaseManager/ControlGroup/MnetList/MnetRecord" ):
                # print( ET.tostring(r) )
                groupList.append({"id": r.get("Group"), "name": r.get("GroupNameWeb")})
            await websocket.close()
            return groupList

    def getDevices(self):
        return runner.run_async_safely(self.getDevicesAsync())

    async def getDeviceInfoAsync(self, deviceId, clean=True):
        """:param deviceId: The numeric ID of the device to get
        :param clean: if True (default), then remove keys with empty values.
        """
        if AE200_SIMULATOR:
            raise RuntimeError("AE200_SIMULATOR not compatiable with AE200Functions")
        async with websockets.connect( f"ws://{self.address}/b_xmlproc/",
                                       extensions=[permessage_deflate.ClientPerMessageDeflateFactory()],
                                       origin=f"http://{self.address}",
                                       subprotocols=["b_xmlproc"], ) as websocket:
            getMnetDetailsPayload = getMnetDetails([deviceId])
            await websocket.send(getMnetDetailsPayload)
            mnetDetailsResultStr = await websocket.recv()
            mnetDetailsResultXML = ET.fromstring(mnetDetailsResultStr)

            # result = {}
            node = mnetDetailsResultXML.find("./DatabaseManager/Mnet")
            await websocket.close()
            return cleanDeviceInfo(node.attrib) if clean else node.attrib

    def getDeviceInfo(self, deviceId, clean=True):
        return runner.run_async_safely(self.getDeviceInfoAsync(deviceId, clean=clean))

    async def sendAsync(self, deviceId, attributes):
        assert 'PYTEST' not in os.environ
        if AE200_SIMULATOR:
            raise RuntimeError("AE200_SIMULATOR not compatiable with AE200Functions")
        async with websockets.connect(
            f"ws://{self.address}/b_xmlproc/",
            extensions=[permessage_deflate.ClientPerMessageDeflateFactory()],
            origin=f"http://{self.address}",
            subprotocols=["b_xmlproc"],
        ) as websocket:
            attrs = " ".join([f'{key}="{attributes[key]}"' for key in attributes])
            payload = setRequestPayload.format(deviceId=deviceId, attrs=attrs)
            await websocket.send(payload)
            await websocket.close()

    def send(self, deviceId, attributes):
        return runner.run_async_safely(self.sendAsync(deviceId, attributes))

async def get_dev_status(unit_id):
    d = AE200Functions()
    return await d.getDeviceInfoAsync(unit_id)

async def get_devices_async():
    d = AE200Functions()
    return await d.getDevicesAsync()

async def set_fan_speed_async(device, speed):
    logger.info("set_fan_speed_async(%s,%s)",device,speed)
    d = AE200Functions()
    await d.sendAsync(device, {"FanSpeed": FAN_SPEEDS[speed]})

async def set_drive_async(device, drive_int):
    drive_str = int_to_drive(drive_int)
    logger.error("set_drive_async(%s,%s,%s)",device,drive_int,drive_str)
    d = AE200Functions()
    await d.sendAsync(device, {"Drive": drive_str})

async def get_device_info_async(device):
    logger.info("get_device_info_async(%s)",device)
    d = AE200Functions()
    return await d.getDeviceInfoAsync(device)


################################################################
## Everything after here works with the simulator
################################################################

simulated_devices = {}
DEVICES='devices'
if AE200_SIMULATOR:
    logger.debug("SIMULATOR ENABLED")
    simulated_devices[DEVICES] = json.loads( (SIMULATOR_DIR / 'ae200_get_devices.json').read_bytes())
    for dev in simulated_devices[DEVICES]:
        did = dev['id']
        simulated_devices[did] = json.loads( (SIMULATOR_DIR / f'ae200_get_device_{did}.json').read_bytes())


def set_drive(ae200_device, drive_int):
    drive_str = int_to_drive(drive_int)
    logger.info("set_fan_speed(%s,%s,%s)",ae200_device,drive_int,drive_str)

    if AE200_SIMULATOR:
        simulated_devices[str(ae200_device)]['Drive'] = drive_str
        return

    d = AE200Functions()
    d.send(ae200_device, {"Drive": drive_str})

def set_fan_speed(ae200_device, speed):
    fan_speed = FAN_SPEEDS[speed]
    logger.info("set_fan_speed(%s,%s)=%s",ae200_device,speed,fan_speed)
    if AE200_SIMULATOR:
        simulated_devices[str(ae200_device)]['FanSpeed'] = fan_speed
        return
    d = AE200Functions()
    d.send(ae200_device, {"FanSpeed": fan_speed})

def get_device_info(device):
    logger.info("get_device_info(%s)",device)
    if AE200_SIMULATOR:
        return simulated_devices[str(device)]

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
        formatter_class=argparse.ArgumentDefaultsHelpFormatter )
    parser.add_argument( "--host", help='address of the AE200 controller')
    parser.add_argument( "--json", help='Full JSON dump of the device(s)', action="store_true")
    parser.add_argument( "--level", help="Specify level 0-4. 0 is off", type=int, default=0 )
    args = parser.parse_args()

    d = AE200Functions(args.host)

    # Test reading device list
    devs = get_devices()
    print(json.dumps(devs))

    for dev in devs:
        did = dev["id"]
        name = dev['name']
        # print(did, json.dumps(d.getDeviceInfo(did), indent=4))
        data = get_device_info(did)
        print(did, name, "drive: ", data["Drive"], "fan speed: ", data["FanSpeed"])

    if args.json:
        for dev in args.devices:
            did = int(dev)
            data = get_device_info(did)
            print(json.dumps(data,indent=4,default=str))
