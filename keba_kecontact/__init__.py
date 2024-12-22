"""Init file for keba_kecontact."""

import asyncio

from .connection import KebaKeContact


async def create_keba_connection(
    loop: asyncio.AbstractEventLoop | None = None, timeout: int = 3, bind_ip: str = "0.0.0.0"
) -> KebaKeContact:
    """Create a KebaKeContact object as keba connection handler.

    Args:
        loop (asyncio.AbstractEventLoop | None, optional): asyncio loop. Defaults to None.
        timeout (int, optional): timeout for charging station. Defaults to 3 seconds.
        bind_ip (str, optional): bind IP address. Defaults to "0.0.0.0".

    Returns:
        KebaKeContact: keba connection handler

    """
    loop = asyncio.get_event_loop() if loop is None else loop
    keba_connection = KebaKeContact(loop, timeout)
    await keba_connection.init_socket(bind_ip)
    return keba_connection
