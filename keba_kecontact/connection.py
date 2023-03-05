from __future__ import annotations

import asyncio
import json
import logging
import socket

import asyncio_dgram

from keba_kecontact.wallbox import Wallbox, WallboxDeviceInfo

_LOGGER = logging.getLogger(__name__)

UDP_PORT = 7090


class SingletonMeta(type):
    """Singleton base class"""

    _instances = {}

    def __call__(cls, *args, **kwargs):
        """
        Possible changes to the value of the `__init__` argument do not affect
        the returned instance.
        """
        if cls not in cls._instances:
            instance = super().__call__(*args, **kwargs)
            cls._instances[cls] = instance
        return cls._instances[cls]


class KebaKeContact(metaclass=SingletonMeta):
    """Keba-KeContact base clase to handle connections to wallboxes"""

    def __init__(self, loop: asyncio.AbstractEventLoop | None = None, timeout: int = 3):
        """Constructor."""
        self._loop: asyncio.AbstractEventLoop = (
            asyncio.get_event_loop() if loop is None else loop
        )

        self._stream = None
        self._wallbox_map = dict()
        self._sending_lock = asyncio.Lock()

        self._timeout: int = timeout

        # discovery
        self._discovery_event: asyncio.Event = asyncio.Event()
        self._discovery_event.set()
        self._found_hosts: list[str] = []

        # device info fetching
        self._device_info_event: asyncio.Event = asyncio.Event()
        self._device_info_event.set()
        self._device_info_host: str = ""
        self._device_info: WallboxDeviceInfo | None = None

    async def discover_devices(self, broadcast_addr: str) -> list[str]:
        """Method to start a discovery

        Args:
            broadcast_addr (str): IP Address to send discvoery message to,
                should be a network broadcast address

        Returns:
            List[str]: List of found hosts
        """
        _LOGGER.info("Discover devices in %s", broadcast_addr)

        self._discovery_event.clear()
        await self.send(broadcast_addr, "i")

        # As we do not know how many wallboxes to find, wait for a certain time
        await asyncio.sleep(self._timeout)

        self._discovery_event.set()
        return self._found_hosts

    async def get_device_info(self, host: str) -> WallboxDeviceInfo:
        """Method to get device info for a wallbox with given host

        Args:
            host (str): host or IP address to get device info from

        Raises:
            SetupError: Setup error will occure if timeout is reached

        Returns:
            WallboxDeviceInfo: Wallbox device info
        """
        async with asyncio.Lock():
            _LOGGER.debug("Requesting device info from %s", host)

            self._device_info_event.clear()
            self._device_info_host = host

            await self.send(host, "report 1")

            # Wait for positive response from host
            try:
                await asyncio.wait_for(
                    self._device_info_event.wait(), timeout=self._timeout
                )
            except asyncio.TimeoutError as exc:
                _LOGGER.warning(
                    "Wallbox at %s has not replied within %ds. Abort.",
                    host,
                    self._timeout,
                )
                raise SetupError("Could not get device info") from exc
            return self._device_info

    async def setup_wallbox(self, host: str, **kwargs) -> Wallbox:
        """Setup wallbox into the connection handler

        Args:
            host (str): host of wallbox to add to the connection handler

        Returns:
            Wallbox: Wallbox object to handle functions and readings
        """
        _LOGGER.debug("Start connecting to %s", host)

        # check if wallbox is already configured
        if host in self._wallbox_map:
            _LOGGER.info(
                "Wallbox at %s already configured. Return existing object.", host
            )
            return self._wallbox_map.get(host)

        # Get device info and create wallbox object and add it to observing map
        device_info = await self.get_device_info(host)

        for wb in self.get_wallboxes():
            if wb.device_info.device_id == device_info.device_id:
                _LOGGER.info(
                    "Found same wallbox (Serial: %s %s) on a different IP address (%s). Updating device info.",
                    device_info.device_id,
                    wb.device_info.host,
                    device_info.host,
                )
                # update map key
                self._wallbox_map[host] = self._wallbox_map.pop(wb.device_info.host)

                # upadte wallbox device info
                wb.update_device_info(device_info)
                return wb

        # Wallbox not known, thus create a new instance for it
        wallbox = Wallbox(self, device_info, self._loop, **kwargs)
        self._wallbox_map.update({host: wallbox})

        _LOGGER.info(
            "%s Wallbox (Serial: %s) at %s successfully connected.",
            device_info.manufacturer,
            device_info.device_id,
            device_info.host,
        )
        return wallbox

    def remove_wallbox(self, host: str) -> None:
        """Remove wallbox from the connection handler.

        Args:
            host (str): host of the wallbox
        """
        if host in self._wallbox_map:
            wb = self.get_wallbox(host)
            wb.stop_periodic_request()
            self._wallbox_map.pop(host)
            _LOGGER.debug("Wallbox at %s removed.", host)
        else:
            _LOGGER.warning(
                "Wallbox at %s could not be removed as it was not configured.", host
            )

    def get_wallboxes(self) -> list(Wallbox):
        """Get a list of all configured wallboxes

        Returns:
            list(Wallbox): list of Wallbox bjects
        """
        return list(self._wallbox_map.values())

    def get_wallbox(self, host: str) -> Wallbox:
        """Get a specific wallbox by host

        Args:
            host (str): host of wallbox to get

        Returns:
            Wallbox: Wallbox object of given host
        """
        return self._wallbox_map.get(host)

    async def send(self, host: str, payload: str, blocking_time: int = 0.1) -> None:
        """Send a payload to the wallbox with given host

        Args:
            host (str): host of wallbox to send payload to
            payload (str): raw payload to send encoded as cp437
            blocking_time (int): blocking time in seconds. Defaults to 100 ms.
        """
        async with self._sending_lock:
            _LOGGER.debug("Send %s to %s", payload, host)

            # If not yet connected, bind socket and start listening
            if self._stream is None:
                self._stream = await asyncio_dgram.bind(("0.0.0.0", UDP_PORT))

                # Enable broadcast for discovery
                if hasattr(socket, "SO_BROADCAST"):
                    self._stream.socket.setsockopt(
                        socket.SOL_SOCKET, socket.SO_BROADCAST, 1
                    )

                # Start listening on the port to handle responses
                self._loop.create_task(self._listen())
                _LOGGER.debug(
                    "Socket binding created (0.0.0.0) and listening started on port %d.",
                    UDP_PORT,
                )

            await self._stream.send(payload.encode("cp437", "ignore"), (host, UDP_PORT))
            await asyncio.sleep(
                max(blocking_time, 0.1)
            )  # Sleep for blocking time but at least 100 ms

    async def _listen(self) -> None:
        data, remote_addr = await self._stream.recv()  # Listen until something received
        self._loop.create_task(self._listen())  # Listen again
        self._loop.create_task(self._internal_callback(data, remote_addr))  # Callback

    async def _internal_callback(self, data, remote_addr) -> None:
        _LOGGER.debug(
            "Datagram received from %s: %s", str(remote_addr), str(data.decode())
        )
        # Waiting for DeviceInfo (ID 1 report)
        if not self._device_info_event.is_set():
            report_1_json = json.loads(data.decode())
            device_info = WallboxDeviceInfo(remote_addr[0], report_1_json)

            if device_info:
                # Check if requested host
                if device_info.host == self._device_info_host:
                    self._device_info = device_info
                    self._device_info_host = ""
                    self._device_info_event.set()
                else:
                    _LOGGER.warning(
                        "Received device info from another host that was not requested"
                    )
        # Waiting for discovery ("i")
        if not self._discovery_event.is_set():
            if remote_addr not in self._found_hosts:
                if "Firmware" in data.decode():
                    self._found_hosts.append(remote_addr[0])
                    _LOGGER.debug("Found device with IP address %s.", str(remote_addr))

        # Callback datagram received on respective wallbox
        if remote_addr[0] not in self._wallbox_map:
            _LOGGER.debug(
                "Received a message from a not yet registered wallbox at %s.",
                str(remote_addr[0]),
            )
        else:
            wb = self._wallbox_map.get(remote_addr[0])
            self._loop.create_task(wb.datagram_received(data))


class SetupError(Exception):
    """Error to indicate we cannot connect."""
