#!/usr/bin/python3
"""Simple executable to demonstrate and test the usage of the library."""

import asyncio
import logging
import sys
from keba_kecontact.connection import KebaKeContact, SetupError
from keba_kecontact.emulator import Emulator

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(threadName)-12.12s] [%(levelname)-5.5s]  %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
# logging.getLogger("asyncio").setLevel(logging.DEBUG)


async def client_mode(loop):

    keba = KebaKeContact(loop)
    wbs = []

    for ip in sys.argv[1:]:

        try:
            device_info = await keba.get_device_info(ip)
            print(device_info)
            wb = await keba.setup_wallbox(ip)
        except SetupError:
            print(f"Wallbox at {ip} could not be set up. continue with next host")
            continue

        wb.add_callback(callback1)  # Optional
        # wb.add_callback(callback2)  # Optional
        print(wb.device_info)
        # await wb.set_failsafe(0, 0, False)
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

    await asyncio.sleep(10)

    for ip in sys.argv[1:]:
        keba.remove_wallbox(ip)

    print("\n clean \n\n")

    print(keba.get_wallboxes())

    # await keba.setup_wallbox("192.168.170.10")


def callback1(wallbox, data):
    print(f"callback function 1: {wallbox.device_info.device_id}: {data}")


def callback2(wallbox, data):
    print(f"callback function 2: {wallbox.device_info.device_id}: {data}")


async def emulation_mode(loop):
    emu = Emulator(loop)
    await emu.start()
    logging.info("Emulator started.")


if __name__ == "__main__":

    loop = asyncio.get_event_loop()

    if len(sys.argv) < 2:
        print(
            "Add argument 'emu' to start the keba emulator or one or more space separated IP Addresses to starting listening to these wallboxes."
        )
    elif sys.argv[1] == "emu":
        logging.info("Run an emulated Keba Wallbox on port 7090.")
        loop.create_task(emulation_mode(loop))
    else:
        logging.info("Run Keba CLI in client mode to connect to given IP addresses.")
        loop.create_task(client_mode(loop))

    loop.run_forever()
