#!/usr/bin/python3
"""Simple executable to demonstrate and test the usage of the library."""

import argparse
import asyncio
import logging
import sys

import netifaces

from keba_kecontact.connection import create_keba_connection, SetupError
from keba_kecontact.emulator import Emulator

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(threadName)-12.12s] [%(levelname)-5.5s]  %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
# logging.getLogger("asyncio").setLevel(logging.DEBUG)


async def client_mode(ips: list[str]):
    """Running cli in client mode and connect to given charging stations

    Args:
        ips (list[str]): list of ips to connect to
    """
    keba = await create_keba_connection()

    def callback1(charging_station, data):
        print(
            f"Example callback function 1: {charging_station.device_info.device_id}: {data}"
        )

    def callback2(charging_station, data):
        print(
            f"Example callback function 2: {charging_station.device_info.device_id}: {data}"
        )

    for ip in ips[0]:
        try:
            charging_station = await keba.setup_charging_station(ip)
        except SetupError:
            print(
                f"charging station at {ip} could not be set up. continue with next IP address."
            )
            continue

        charging_station.add_callback(callback1)  # Optional
        charging_station.add_callback(callback2)  # Optional
        print(charging_station.device_info)


async def emulation_mode():
    """Starts an emulator"""
    emu = Emulator()
    await emu.start()
    logging.info("Emulator started.")


async def discovery_mode():
    """Starts a discovery on all aailable network interfaces"""
    keba = await create_keba_connection()

    for interface in netifaces.interfaces():
        data = netifaces.ifaddresses(interface)
        ipv4 = data.get(2)
        if ipv4 is not None:
            broadcast_addr = ipv4[0].get("broadcast")
            if broadcast_addr is not None:
                devices = await keba.discover_devices(broadcast_addr=broadcast_addr)
                for host in devices:
                    await keba.setup_charging_station(host)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Add some integers.")
    parser.add_argument("--dis", help="run discovery.", action="store_true")
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
        loop.create_task(emulation_mode())
    elif args.dis:
        logging.info("Run an keba charging station discovery.")
        loop.create_task(discovery_mode())
    elif args.ip:
        logging.info("Run Keba CLI in client mode to connect to given IP addresses.")
        loop.create_task(client_mode(args.ip))
    else:
        logging.info("No argument given, try --help.")

    loop.run_forever()
