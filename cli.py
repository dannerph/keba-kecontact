#!/usr/bin/python3
"""Simple executable to demonstrate and test the usage of the library."""

import asyncio
import logging
import sys
from keba_kecontact.connection import KebaKeContact
from keba_kecontact.emulator import Emulator

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(threadName)-12.12s] [%(levelname)-5.5s]  %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
# logging.getLogger("asyncio").setLevel(logging.DEBUG)


async def client_mode(loop):

    keba = KebaKeContact(loop)
    wbs = []

    for ip in sys.argv[1:]:

        wb = await keba.setup_wallbox(ip)
        if not wb:
            print("Wallbox could not be set up.")
            return

        wb.set_callback(callback)  # Optional
        print(wb.device_info)
        wbs.append(wb)

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
    # await wb1.set_energy(10)
    # wb1.set_output(0)
    # wb1.start("e3f76b8d00000000", "01010400000000000000")
    # wb1.stop("e3f76b8d00000000")
    # wb1.display(1, 0, 0, None, "text")
    # wb1.unlock()


def callback(wallbox, data):
    print(f"{wallbox.device_info.device_id}: {data}")


async def emulation_mode(loop):
    emu = Emulator(loop)
    await emu.start()
    logging.info("Emulator started.")


if __name__ == "__main__":

    loop = asyncio.get_event_loop()

    if len(sys.argv) < 2:
        print("Add argument 'emu' to start the keba emulator or one or more space separated IP Addresses to starting listening to these wallboxes.")
    elif sys.argv[1] == "emu":
        logging.info("Run an emulated Keba Wallbox on port 7090.")
        loop.create_task(emulation_mode(loop))
    else:
        logging.info("Run Keba CLI in client mode to connect to given IP addresses.")
        loop.create_task(client_mode(loop))

    loop.run_forever()
