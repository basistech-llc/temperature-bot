"""
ae200 controller.
Originally from https://github.com/natevoci/ae200.
Includes both async routines and synchronous covers.
"""

# pylint: disable=invalid-name
# pylint: disable=line-too-long
# pylint: disable=missing-function-docstring
# pylint: disable=redefined-outer-name

import os
import asyncio
import xml.etree.ElementTree as ET
import logging
import json

import concurrent.futures
import websockets
from websockets.extensions import permessage_deflate

from app.util import get_config

# Fan mapping speeds
SPEED_AUTO = -1
SPEEDS = {-1:"AUTO", 0: "OFF", 1: "LOW", 2: "MID2", 3: "MID1", 4: "HIGH"}

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

def drive_speed_to_val(drive, speed):
    """Converts an AE200 drive and speed to a single value (-1 for auto)"""
    if drive is None or speed is None:
        return None
    if drive == "OFF":
        return 0
    if speed=="AUTO":
        return -1
    for n, v in SPEEDS.items():
        if speed == v:
            return n
    raise ValueError(f"Unknown drive={drive} speed={speed}")

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
    """Originally from https://github.com/natevoci/ae200"""

    def __init__(self, address=None):
        self._json = None
        self._temp_list = []
        if address is None:
            address = get_config()['ae200']['host']
        self.address = address

    async def getDevicesAsync(self):
        #assert 'PYTEST' not in os.environ
        async with websockets.connect(
            f"ws://{self.address}/b_xmlproc/",
            extensions=[permessage_deflate.ClientPerMessageDeflateFactory()],
            origin=f"http://{self.address}",
            subprotocols=["b_xmlproc"],
        ) as websocket:
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

def extract_status(data):
    """Return a dict with drive/speed/drive_speed_val/has_speed_control"""
    drive = data.get('Drive',None)
    speed = data.get('FanSpeed',None)
    has_speed_control = (drive is not None and speed is not None and speed in SPEEDS.values())
    return {
        'drive': drive,
        'speed': speed,
        'drive_speed_val': drive_speed_to_val(drive, speed),
        'has_speed_control': has_speed_control
    }

async def set_fan_speed_async(device, speed):
    logging.info("set_fan_speed_async(%s,%s)",device,speed)
    d = AE200Functions()
    if speed == 0:
        await d.sendAsync(device, {"Drive": "OFF"})
    else:
        await d.sendAsync(device, {"Drive": "ON"})
        await d.sendAsync(device, {"FanSpeed": SPEEDS[speed]})

def set_fan_speed(ae200_device, speed):
    logging.info("set_fan_speed(%s,%s)",ae200_device,speed)
    d = AE200Functions()
    if speed == 0:
        d.send(ae200_device, {"Drive": "OFF"})
    else:
        d.send(ae200_device, {"Drive": "ON"})
        d.send(ae200_device, {"FanSpeed": SPEEDS[speed]})

async def get_device_info_async(device):
    logging.info("get_device_info_async(%s)",device)
    d = AE200Functions()
    return await d.getDeviceInfoAsync(device)

def get_device_info(device):
    logging.info("get_device_info(%s)",device)
    d = AE200Functions()
    return d.getDeviceInfo(device)

def get_device_speed(device):
    info = get_device_info(device)
    return drive_speed_to_val(info['Drive'], info['FanSpeed'])

def get_devices():
    logging.info("get_devices()")
    d = AE200Functions()
    return d.getDevices()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Demo function",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter )
    parser.add_argument( "--host", help='address of the AE200 controller')
    parser.add_argument( "--json", help='Full JSON dump of the device(s)', action="store_true")
    parser.add_argument( "--set",   help='Specifies a device to set', type=int)
    parser.add_argument( "--level", help="Specify level 0-4. 0 is off", type=int, default=0 )
    args = parser.parse_args()

    d = AE200Functions(args.host)

    # Test reading device list
    devs = d.getDevices()
    print(json.dumps(devs))

    for dev in devs:
        did = dev["id"]
        name = dev['name']
        # print(did, json.dumps(d.getDeviceInfo(did), indent=4))
        data = d.getDeviceInfo(did)
        print(did, name, "drive: ", data["Drive"], "fan speed: ", data["FanSpeed"])

    if args.json:
        for dev in args.devices:
            did = int(dev)
            data = d.getDeviceInfo(did)
            print(json.dumps(data,indent=4,default=str))
