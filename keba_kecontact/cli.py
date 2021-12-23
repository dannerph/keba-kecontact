#!/usr/bin/python3
"""Simple executable to demonstrate and test the usage of the library."""

import asyncio
import logging
import sys
from keba_kecontact.connection import KebaKeContact

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(threadName)-12.12s] [%(levelname)-5.5s]  %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout)
    ])
# logging.getLogger("asyncio").setLevel(logging.DEBUG)

async def main(loop):

    keba_api = KebaKeContact(loop)
    
    ip1 = sys.argv[1]
    wb1 = await keba_api.setup_wallbox(ip1)
    if not wb1:
        print("Wallbox could not be set up.")
        return

    wb1.set_callback(callback) #Optional
    print(wb1.device_info)

    # # Optional for multiple wallboxes
    # ip2 = sys.argv[2]
    # wb2 = await keba_api.setup_wallbox(ip2)
    # wb2.set_callback(callback)
    # print(wb2.deviceInfo)

    # Data examples
    # print(wb1.get_value("uptime_pretty"))
    # print(wb1.get_value("Plug_plugged"))
    # print(wb1.get_value("Plug_wallbox"))
    # print(wb1.get_value("Plug_locked"))
    # print(wb1.get_value("Plug_EV"))
    # print(wb1.get_value("State_on"))
    # print(wb1.get_value("State_details"))
    # print(wb1.get_value("FS_on"))

    # Function examples
    # wb1.set_failsafe(0, 0, 0)
    # wb1.set_ena(True)
    # wb1.set_curr(0)
    # wb1.set_currtime(0, 0)
    await wb1.set_energy(10)
    # wb1.set_output(0)
    # wb1.start("e3f76b8d00000000", "01010400000000000000")
    # wb1.stop("e3f76b8d00000000")
    # wb1.display(1, 0, 0, None, "text")
    # wb1.unlock()

def callback(wallbox, data):
    print(f"{wallbox.device_info.device_id}: {data}")

if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    loop.create_task(main(loop))
    loop.run_forever()
