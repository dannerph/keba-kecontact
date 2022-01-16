from __future__ import annotations

import asyncio
import asyncio_dgram
import logging
import json

from keba_kecontact.wallbox import Wallbox, WallboxDeviceInfo

_LOGGER = logging.getLogger(__name__)

UDP_PORT = 7090


class KebaKeContact:
    def __init__(self, loop=None, device_info_timeout: int = 5):
        """Constructor."""
        self._loop = loop = asyncio.get_event_loop() if loop is None else loop

        self._stream = None
        self._wallbox_map = dict()

        self._device_info_timeout = device_info_timeout
        self._device_info_event = None
        self._device_info_host = None
        self._device_info = None

        self._send_lock = asyncio.Lock()

    async def discover_devices(self):
        raise NotImplementedError()

    async def get_device_info(self, host: str) -> WallboxDeviceInfo:

        _LOGGER.debug(f"Requesting device info from {host}")

        self._device_info_event = asyncio.Event()
        self._device_info_host = host

        await self.send(host, "report 1")

        # Wait for positive response from host
        try:
            await asyncio.wait_for(
                self._device_info_event.wait(), timeout=self._device_info_timeout
            )
        except asyncio.TimeoutError:
            _LOGGER.warning(
                f"Wallbox at {host} has not replied within {self._device_info_timeout }s. Abort."
            )
            raise SetupError("Could not get device info")
        finally:
            self._device_info_event = None

        return self._device_info

    async def setup_wallbox(self, host: str, **kwargs) -> Wallbox:

        _LOGGER.debug(f"Start connecting to {host}")

        # check if wallbox is already configured
        if host in self._wallbox_map:
            _LOGGER.info(
                f"Wallbox at {host} already configured. Return existing object."
            )
            return self._wallbox_map.get(host)

        # Get device info and create wallbox object and add it to observing map
        device_info = await self.get_device_info(host)
        wallbox = Wallbox(self, device_info, self._loop, **kwargs)
        self._wallbox_map.update({host: wallbox})

        _LOGGER.info(
            f"{device_info.manufacturer} Wallbox (Serial: {device_info.device_id}) at {device_info.host} successfully connected."
        )
        return wallbox

    def remove_wallbox(self, host: str) -> None:
        if host in self._wallbox_map:
            wb = self.get_wallbox(host)
            wb.stop_periodic_request()
            self._wallbox_map.pop(host)
            _LOGGER.debug(f"Wallbox at {host} removed.")
        else:
            _LOGGER.warning(
                f"Wallbox at {host} could not be removed as it was not configured."
            )

    def get_wallboxes(self) -> list(Wallbox):
        return list(self._wallbox_map.values())

    def get_wallbox(self, host) -> Wallbox:
        return self._wallbox_map.get(host)

    async def send(self, host: str, payload: str) -> None:
        _LOGGER.debug("Send %s to %s", payload, host)

        # Bind socket and start listening if not yet done
        if self._stream is None:
            self._stream = await asyncio_dgram.bind(("0.0.0.0", UDP_PORT))
            self._loop.create_task(self._listen())
            _LOGGER.debug(
                f"Socket binding created (0.0.0.0) and listening started on port {UDP_PORT}."
            )

        async with self._send_lock:
            await self._stream.send(payload.encode("cp437", "ignore"), (host, UDP_PORT))
            await asyncio.sleep(0.1)  # Sleep for 100ms as given in the manual

    async def _listen(self) -> None:
        data, remote_addr = await self._stream.recv()  # Listen until something received
        self._loop.create_task(self._listen())  # Listen again
        self._loop.create_task(self._internal_callback(data, remote_addr))  # Callback

    async def _internal_callback(self, data, remote_addr) -> None:
        _LOGGER.debug(f"Datagram recvied from {remote_addr}: {data.decode()!r}")

        if self._device_info_event:  # waiting for an ID 1 report
            report_1_json = json.loads(data.decode())
            device_info = WallboxDeviceInfo(remote_addr[0], report_1_json)

            if device_info:
                # Check if requested host
                if device_info.host == self._device_info_host:
                    self._device_info = device_info
                    self._device_info_host = None
                    self._device_info_event.set()
                else:
                    _LOGGER.warning(
                        "Received device info from another host that was not requested"
                    )

        # callback datagram received on respective wallbox
        if remote_addr[0] not in self._wallbox_map:
            _LOGGER.debug("Received something from a not yet registered wallbox.")
        else:
            wb = self._wallbox_map.get(remote_addr[0])
            self._loop.create_task(wb.datagram_received(data))


class SetupError(Exception):
    """Error to indicate we cannot connect."""
