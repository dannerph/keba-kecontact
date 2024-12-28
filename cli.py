#!/usr/bin/python3
"""Simple executable to demonstrate and test the usage of the library."""

import argparse
import asyncio
import inspect
import ipaddress
import logging
import sys

from ifaddr import get_adapters

from keba_kecontact import create_keba_connection
from keba_kecontact.connection import ChargingStation
from keba_kecontact.emulator import Emulator
from keba_kecontact.utils import SetupError

logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s [%(levelname)-5.5s]  %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logging.getLogger("asyncio").setLevel(logging.WARNING)


async def client_mode(ip: str) -> None:
    """Run cli in client mode and connect to given charging stations.

    Args:
        ip (str): IP address to connect to

    """
    keba = await create_keba_connection()
    try:
        charging_station = await keba.setup_charging_station(ip, periodic_request=False)
    except SetupError as ex:
        print(f"Charging station at {ip} could not be set up: {ex}")
        loop = asyncio.get_event_loop()
        loop.stop()
        return

    # Extract valid commands
    method_list = [
        func
        for func in dir(ChargingStation)
        if callable(getattr(ChargingStation, func))
        and not func.startswith("__")
        and not func.startswith("_")
    ]
    for m in ["add_callback", "datagram_received", "update_device_info", "stop_periodic_request"]:
        method_list.remove(m)

    async def async_input(prompt: str = "") -> str:
        return await asyncio.to_thread(input, prompt)

    print("Connected. For help type ? or help")
    while True:
        command = await async_input("> ")
        if "exit" in command:
            loop = asyncio.get_event_loop()
            loop.stop()
            return
        args = command.split(" ")
        if args[0] in method_list:
            func = getattr(charging_station, args[0])
            params = args[1:]
            try:
                result = await func(*params) if inspect.iscoroutinefunction(func) else func(*params)
                if result:
                    print(result)
            except (TypeError, ValueError, NotImplementedError) as ex:
                print(ex)
        else:
            print('Exit the udp command prompt by typing "exit"')
            print("The following commands are available:")
            for m in method_list:
                func = getattr(charging_station, m)
                print("  ", m, end="")
                sig = inspect.signature(func)
                if len(sig.parameters) > 0:
                    for param_name, param in sig.parameters.items():
                        default_value = (
                            "=" + str(param.default)
                            if param.default is not inspect.Parameter.empty
                            else ""
                        )
                        print(" [", param_name, default_value, "]", end="", sep="")
                print()


async def emulation_mode() -> None:
    """Start an emulator."""
    emu = Emulator()
    await emu.start()
    print("Emulator started")


async def discovery_mode() -> None:
    """Start a discovery on all available network interfaces."""
    keba = await create_keba_connection()

    for adapter in get_adapters():
        for ip in adapter.ips:
            if ip.is_IPv4:
                network = ipaddress.ip_network(ip.ip + "/" + str(ip.network_prefix), strict=False)
                devices = await keba.discover_devices(broadcast_addr=str(network.broadcast_address))
                if not devices:
                    print("Not device found in subnet", network)
                for dev in devices:
                    print("Found devices at", dev)

    loop = asyncio.get_event_loop()
    loop.stop()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="With this CLI you can discover, connect or emulate KEBA charging stations."
    )
    parser.add_argument("--debug", help="enable debug logs", action="store_true")
    parser.add_argument("--dis", help="run discovery", action="store_true")
    parser.add_argument("--emu", help="run charging station emulator", action="store_true")
    parser.add_argument("--ip", help="IP to connect to", action="store")

    args = parser.parse_args()
    task = None

    # Logging
    if args.debug:
        logging.getLogger("keba_kecontact").setLevel(logging.DEBUG)

    # Mode
    if args.emu:
        print("Start emulator on port 7090")
        task = emulation_mode()
    elif args.dis:
        print("Start discovery")
        task = discovery_mode()
    elif args.ip:
        print("Connect to", args.ip)
        task = client_mode(args.ip)
    else:
        print("No argument given, try --help")

    # Run task
    if task:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.create_task(task)  # noqa: RUF006
        loop.run_forever()
