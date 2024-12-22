#!/usr/bin/python3
"""Simple executable to demonstrate and test the usage of the library."""

import argparse
import asyncio
import ipaddress
import logging
import sys

from ifaddr import get_adapters

from keba_kecontact import create_keba_connection
from keba_kecontact.connection import ChargingStation
from keba_kecontact.emulator import Emulator
from keba_kecontact.utils import SetupError

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(threadName)-12.12s] [%(levelname)-5.5s]  %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
# logging.getLogger("asyncio").setLevel(logging.DEBUG)


async def client_mode(ips: list[str]) -> None:
    """Run cli in client mode and connect to given charging stations.

    Args:
        ips (list[str]): list of ips to connect to

    """
    keba = await create_keba_connection()

    def callback1(charging_station: ChargingStation, data: dict[str, str]) -> None:
        print(f"Example callback function 1: {charging_station.device_info.device_id}: {data}")

    def callback2(charging_station: ChargingStation, data: dict[str, str]) -> None:
        print(f"Example callback function 2: {charging_station.device_info.device_id}: {data}")

    for ip in ips[0]:
        try:
            charging_station = await keba.setup_charging_station(ip)
        except SetupError:
            print(f"Charging station at {ip} could not be set up.")
            continue

        charging_station.add_callback(callback1)  # Optional
        charging_station.add_callback(callback2)  # Optional
        print(charging_station.device_info)
        await charging_station.set_current_max_permanent(63)
        await charging_station.set_current(12, 1)


async def emulation_mode() -> None:
    """Start an emulator."""
    emu = Emulator()
    await emu.start()
    logging.info("Emulator started.")


async def discovery_mode() -> None:
    """Start a discovery on all available network interfaces."""
    keba = await create_keba_connection()

    for adapter in get_adapters():
        for ip in adapter.ips:
            if ip.is_IPv4:
                network = ipaddress.ip_network(ip.ip + "/" + str(ip.network_prefix), strict=False)
                devices = await keba.discover_devices(broadcast_addr=str(network.broadcast_address))
                for host in devices:
                    await keba.setup_charging_station(host)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Add some integers.")
    parser.add_argument("--dis", help="run discovery.", action="store_true")
    parser.add_argument("--emu", help="run charging station emulator", action="store_true")
    parser.add_argument("--ip", help="list of IPs to connect to.", action="append", nargs="+")

    args = parser.parse_args()

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    if args.emu:
        logging.info("Run an emulated Keba charging station on port 7090.")
        loop.create_task(emulation_mode())  # noqa: RUF006
    elif args.dis:
        logging.info("Run an keba charging station discovery.")
        loop.create_task(discovery_mode())  # noqa: RUF006
    elif args.ip:
        logging.info("Run Keba CLI in client mode to connect to given IP addresses.")
        loop.create_task(client_mode(args.ip))  # noqa: RUF006
    else:
        logging.info("No argument given, try --help.")

    loop.run_forever()
