"""
ae200 controller.
Originally from https://github.com/natevoci/ae200.
Includes both async routines and synchronouse covers.
"""

# pylint: disable=invalid-name
# pylint: disable=line-too-long
# pylint: disable=missing-function-docstring
# pylint: disable=redefined-outer-name

import asyncio
import xml.etree.ElementTree as ET
import logging
import json

import websockets
from websockets.extensions import permessage_deflate

from app.util import get_config

# Fan mapping speeds
SPEED_AUTO = -1
SPEEDS = {-1:"AUTO", 1: "LOW", 2: "MID2", 3: "MID1", 4: "HIGH"}

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
    if drive == "OFF":
        return 0
    if speed=="AUTO":
        return -1
    for n, v in SPEEDS.items():
        if speed == v:
            return n
    raise ValueError(f"Unknown drive={drive} speed={speed}")

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
        return asyncio.run(self.getDevicesAsync())

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
        return asyncio.run(self.getDeviceInfoAsync(deviceId, clean=clean))

    async def sendAsync(self, deviceId, attributes):
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
        return asyncio.run(self.sendAsync(deviceId, attributes))

async def get_dev_status(dev):
    d = AE200Functions()
    return await d.getDeviceInfoAsync(dev)

async def get_system_map():
    d = AE200Functions()
    ret = {}
    all_items = await d.getDevicesAsync()
    for item in all_items:
        dev = item['id']
        name = item['name']
        ret[dev] = name
    return ret

def extract_status(data):
    """Return a dict with drive/speed/drive_speed_val"""
    return {
        'drive': data['Drive'],
        'speed': data['FanSpeed'],
        'drive_speed_val': drive_speed_to_val(data['Drive'], data['FanSpeed']),
    }

async def get_all_status():
    d = AE200Functions()
    ret = {}
    all_items = await d.getDevicesAsync()
    for item in all_items:
        dev = item['id']
        data = await d.getDeviceInfoAsync(dev)
        try:
            ret = {**extract_status(data), **{'name':item['name']}}
        except KeyError as e:
            logging.error("KeyError '%s' in data: %s", e, data)
    return ret

async def set_fan_speed(device, speed):
    d = AE200Functions()
    if speed == 0:
        await d.sendAsync(device, {"Drive": "OFF"})
    else:
        await d.sendAsync(device, {"Drive": "ON"})
        await d.sendAsync(device, {"FanSpeed": SPEEDS[speed]})


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
