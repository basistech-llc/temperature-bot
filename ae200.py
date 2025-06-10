"""
ae200 controller.
Originally from https://github.com/natevoci/ae200
"""

import logging
import asyncio
import websockets
from websockets.extensions import permessage_deflate
import xml.etree.ElementTree as ET
from pprint import pprint




# logging.basicConfig(
#     format="%(asctime)s %(message)s",
#     level=logging.INFO,
# )

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

def getMnetDetails(deviceIds):
    mnets = "\n".join([f'<Mnet Group="{deviceId}" Drive="*" Vent24h="*" Mode="*" VentMode="*" ModeStatus="*" SetTemp="*" SetTemp1="*" SetTemp2="*" SetTemp3="*" SetTemp4="*" SetTemp5="*" SetHumidity="*" InletTemp="*" InletHumidity="*" AirDirection="*" FanSpeed="*" RemoCon="*" DriveItem="*" ModeItem="*" SetTempItem="*" FilterItem="*" AirDirItem="*" FanSpeedItem="*" TimerItem="*" CheckWaterItem="*" FilterSign="*" Hold="*" EnergyControl="*" EnergyControlIC="*" SetbackControl="*" Ventilation="*" VentiDrive="*" VentiFan="*" Schedule="*" ScheduleAvail="*" ErrorSign="*" CheckWater="*" TempLimitCool="*" TempLimitHeat="*" TempLimit="*" CoolMin="*" CoolMax="*" HeatMin="*" HeatMax="*" AutoMin="*" AutoMax="*" TurnOff="*" MaxSaveValue="*" RoomHumidity="*" Brightness="*" Occupancy="*" NightPurge="*" Humid="*" Vent24hMode="*" SnowFanMode="*" InletTempHWHP="*" OutletTempHWHP="*" HeadTempHWHP="*" OutdoorTemp="*" BrineTemp="*" HeadInletTempCH="*" BACnetTurnOff="*" AISmartStart="*"  />' for deviceId in deviceIds])
    return f"""<?xml version="1.0" encoding="UTF-8" ?>
<Packet>
<Command>getRequest</Command>
<DatabaseManager>
{mnets}
</DatabaseManager>
</Packet>
"""

class AE200Functions:
    def __init__(self):
        self._json = None
        self._temp_list = []

    async def getDevicesAsync(self, address):
        async with websockets.connect(
                f"ws://{address}/b_xmlproc/",
                extensions=[permessage_deflate.ClientPerMessageDeflateFactory()],
                origin=f'http://{address}',
                subprotocols=['b_xmlproc']
            ) as websocket:

            await websocket.send(getUnitsPayload)
            unitsResultStr = await websocket.recv()
            unitsResultXML = ET.fromstring(unitsResultStr)

            groupList = []
            for r in unitsResultXML.findall('./DatabaseManager/ControlGroup/MnetList/MnetRecord'):
                groupList.append({
                    "id": r.get('Group'),
                    "name": r.get('GroupNameWeb')
                })

            await websocket.close()

            return groupList

    def getDevices(self, address):
        return asyncio.run(self.getDevicesAsync(address))


    async def getDeviceInfoAsync(self, address, deviceId):
        async with websockets.connect(
                f"ws://{address}/b_xmlproc/",
                extensions=[permessage_deflate.ClientPerMessageDeflateFactory()],
                origin=f'http://{address}',
                subprotocols=['b_xmlproc']
            ) as websocket:

            getMnetDetailsPayload = getMnetDetails([deviceId])
            await websocket.send(getMnetDetailsPayload)
            mnetDetailsResultStr = await websocket.recv()
            mnetDetailsResultXML = ET.fromstring(mnetDetailsResultStr)

            result = {}
            node = mnetDetailsResultXML.find('./DatabaseManager/Mnet')

            await websocket.close()

            return node.attrib

    def getDeviceInfo(self, address, deviceId):
        return asyncio.run(self.getDeviceInfoAsync(address, deviceId))


    async def sendAsync(self, address, deviceId, attributes):
        async with websockets.connect(
                f"ws://{address}/b_xmlproc/",
                extensions=[permessage_deflate.ClientPerMessageDeflateFactory()],
                origin=f'http://{address}',
                subprotocols=['b_xmlproc']
            ) as websocket:

            attrs = " ".join([f'{key}="{attributes[key]}"' for key in attributes])
            payload = f"""<?xml version="1.0" encoding="UTF-8" ?>
<Packet>
<Command>setRequest</Command>
<DatabaseManager>
<Mnet Group="{deviceId}" {attrs}  />
</DatabaseManager>
</Packet>
"""
            await websocket.send(payload)
            await websocket.close()

    def send(self, address, deviceId, attributes):
        return asyncio.run(self.sendAsync(address, deviceId, attributes))


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description='Set the BasisTech ERVs',
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('--level', help='Specify level 0-4. 0 is off',type=int,default=0)
    parser.add_argument('devices',help='Device. Should be "kitchen" or "bathroom"',nargs='+')
    args = parser.parse_args()


    d = AE200Functions()
    address = "10.2.1.20"

    # Test reading device list
    #pprint(d.getDevices(address))

    ERVS = {'kitchen':'12',
            'bathroom':'13'}

    SPEEDS = {1:'LOW',
              2: 'MID2',
              3: 'MID1',
              4: 'HIGH'}

    for dev in args.devices:
        try:
            num = ERVS[dev.lower()]
        except KeyError:
            print(f"invalid device '{dev}' must be {' or '.join(ERVS.keys())}")
            exit(1)
        if args.level==0:
            d.send(address, num, { "Drive": "OFF"})
        else:
            d.send(address, num, { "Drive": "ON"})
            d.send(address, num, { "FanSpeed": SPEEDS[args.level]})

    for (name,dev) in ERVS.items():
        data = d.getDeviceInfo(address, dev)
        print(dev, name,  "drive: ",data['Drive'], "fan speed: ",data['FanSpeed'])
