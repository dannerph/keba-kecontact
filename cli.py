#!/usr/bin/python3
"""Simple executable to demonstrate and test the usage of the library."""

import asyncio
import logging
import sys
import argparse

import netifaces

from keba_kecontact.connection import KebaKeContact, SetupError
from keba_kecontact.emulator import Emulator

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(threadName)-12.12s] [%(levelname)-5.5s]  %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
# logging.getLogger("asyncio").setLevel(logging.DEBUG)

INTERVAL = 10


async def client_mode(loop, ips):

    keba = KebaKeContact(loop)
    wbs = []

    def callback1(wallbox, data):
        print(f"callback function 1: {wallbox.device_info.device_id}: {data}")

    def callback2(wallbox, data):
        print(f"callback function 2: {wallbox.device_info.device_id}: {data}")

    for ip in ips[0]:

        try:
            device_info = await keba.get_device_info(ip)
            wb = await keba.setup_wallbox(ip, refresh_interval=5, periodic_request=True)
        except SetupError:
            print(
                f"Wallbox at {ip} could not be set up. continue with next IP address."
            )
            continue

        wb.add_callback(callback1)  # Optional
        # wb.add_callback(callback2)  # Optional
        print(wb.device_info)

        await wb.request_data()

        # await asyncio.sleep(INTERVAL)

        # await wb.set_ena(True)

        # await asyncio.sleep(INTERVAL)
        # await wb.set_charging_power(2.3, False)
        # print("2.3 kW")

        # await asyncio.sleep(INTERVAL)
        # await wb.set_charging_power(0.5, False)
        # print("0.5 kW")

        # # await asyncio.sleep(INTERVAL)
        # # await wb.set_charging_power(45.0, False)
        # # print("45 kW")

        # await asyncio.sleep(INTERVAL)
        # await wb.set_charging_power(0, False)
        # print("0 kW")

        # await asyncio.sleep(INTERVAL)
        # await wb.set_charging_power(2.3, False)
        # print("2.3 kW")
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

    # await asyncio.sleep(2)

    # for ip in sys.argv[1:]:
    #     keba.remove_wallbox(ip)

    # print(keba.get_wallboxes())

    # await keba.setup_wallbox("192.168.170.10")


async def emulation_mode(loop):
    emu = Emulator(loop)
    await emu.start()
    logging.info("Emulator started.")


async def discovery_mode(loop):
    keba = KebaKeContact(loop)

    for interface in netifaces.interfaces():
        data = netifaces.ifaddresses(interface)
        ipv4 = data.get(2)
        if ipv4 is not None:
            broadcast_addr = ipv4[0].get("broadcast")
            devices = await keba.discover_devices(broadcast_addr=broadcast_addr)
            logging.info(f"Discovered devices: {devices}")
            for d in devices:
                await keba.setup_wallbox(
                    host=d, refresh_interval=10, periodic_request=True
                )


if __name__ == "__main__":

    parser = argparse.ArgumentParser(description="Add some integers.")
    parser.add_argument(
        "--emu", help="run charging station emulator", action="store_true"
    )
    parser.add_argument(
        "--ip", help="list of IPs to connect to.", action="append", nargs="+"
    )

    args = parser.parse_args()

    loop = asyncio.get_event_loop()
    if args.emu:
        logging.info("Run an emulated Keba charging station on port 7090.")
        loop.create_task(emulation_mode(loop))
    elif args.ip:
        logging.info("Run Keba CLI in client mode to connect to given IP addresses.")
        loop.create_task(client_mode(loop, args.ip))
    else:
        logging.info(
            "No IPs given to connect, trying to discovery the charging stations."
        )
        loop.create_task(discovery_mode(loop))
    loop.run_forever()
