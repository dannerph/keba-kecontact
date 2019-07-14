#!/usr/bin/python3
"""Simple executable to demonstrate and test the usage of the library."""

import asyncio
import logging
import sys
from keba_kecontact import KebaKeContact

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(threadName)-12.12s] [%(levelname)-5.5s]  %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout)
    ])


async def main(ip):
    keba = KebaKeContact(ip, callback)
    await keba.request_data()
    await keba.set_failsafe(0, 0, 0)
    await keba.set_energy()


def callback(data):
    print(data)


if __name__ == '__main__':
    ip = sys.argv[1]
    loop = asyncio.get_event_loop()
    loop.create_task(main(ip))
    loop.run_forever()
