"""Implementation of a Keba charging station"""

import asyncio
import json
import logging
import socket
import threading
from enum import Enum
from typing import Any

import asyncio_dgram

from keba_kecontact.chargingstation import ChargingStation, ChargingStationInfo
from keba_kecontact.const import ID

_LOGGER = logging.getLogger(__name__)

UDP_PORT = 7090


class KebaResponse(Enum):
    """Enum to define different keba responses"""

    BASIC_INFO = "i"
    REPORT_1 = "report 1"
    REPORT_2 = "report 2"
    REPORT_3 = "report 3"
    REPORT_1XX = "report 1xx"
    TCH_OK = "TCH-OK"
    TCH_ERR = "TCH-ERR"
    PUSH_UPDATE = "push update"
    BROADCAST = "broadcast"
    UNKNOWN = "unknown"


def get_response_type(payload: str) -> KebaResponse:
    """Method to get the response type

    Args:
        payload (str): payload of response from Keba charging station

    Returns:
        KebaResponseType: repsonse type of the response
    """
    if payload.startswith("i"):
        return KebaResponse.BROADCAST

    if payload.startswith('"Firmware'):
        return KebaResponse.BASIC_INFO

    if "TCH-OK :done" in payload:
        return KebaResponse.TCH_OK

    if "TCH-ERR" in payload:
        return KebaResponse.TCH_ERR

    json_rcv = json.loads(payload)
    if ID in json_rcv:
        if int(json_rcv[ID]) == 1:
            return KebaResponse.REPORT_1
        if int(json_rcv[ID]) == 2:
            return KebaResponse.REPORT_2
        if int(json_rcv[ID]) == 3:
            return KebaResponse.REPORT_3
        if int(json_rcv[ID]) > 100:
            return KebaResponse.REPORT_1XX

    # TODO: PUSH_UPDATE
    else:
        return KebaResponse.UNKNOWN


class SingletonMeta(type):
    """Singleton base class"""

    _instance = None
    _lock = threading.Lock()

    def __call__(cls, *args, **kwargs):
        """
        Possible changes to the value of the `__init__` argument do not affect
        the returned instance.
        """
        if cls._instance is None:
            with cls._lock:
                if not cls._instance:
                    cls._instance = super().__call__(*args, **kwargs)
        return cls._instance


class KebaKeContact(metaclass=SingletonMeta):
    """Keba-KeContact base clase to handle connections to charging stations"""

    def __init__(
        self,
        loop: asyncio.AbstractEventLoop,
        timeout: int,
    ):
        """Constructor."""
        self._loop = loop

        # Data structures
        self._charging_stations: dict[str, ChargingStation] = {}
        self._timeout: int = timeout
        self._waiting_list: dict[(KebaResponse, str), asyncio.Event] = {}
        self._waiting_response: dict[(KebaResponse, str), Any] = {}

        self._sending_lock: asyncio.Lock = asyncio.Lock()
        self._stream: asyncio_dgram.DatagramServer = None

    ####################################################
    #             Connection management                #
    ####################################################

    async def init_socket(self, bind_ip: str):
        """Method to initialize communication

        Args:
            bind_ip (str): IP address to bind the socket to
        """

        # Block sending until stream is setup
        async with self._sending_lock:
            if self._stream is not None:
                # Skip if already initialized
                return

            self._stream = await asyncio_dgram.bind((bind_ip, UDP_PORT))

            # Enable broadcast for discovery
            if hasattr(socket, "SO_BROADCAST"):
                self._stream.socket.setsockopt(
                    socket.SOL_SOCKET, socket.SO_BROADCAST, 1
                )

            # Start listening on the port to handle responses
            async def listen() -> None:
                data, remote_addr = await self._stream.recv()
                self._loop.create_task(listen())
                self._loop.create_task(self._internal_callback(data, remote_addr))

            self._loop.create_task(listen())
            _LOGGER.debug(
                "Socket binding created (%s) and listening started on port %d.",
                bind_ip,
                UDP_PORT,
            )

    async def _internal_callback(self, data, remote_addr) -> None:
        host = remote_addr[0]
        data = data.decode()
        _LOGGER.debug("Datagram received from %s: %s", host, data.rstrip())

        response_type = get_response_type(data)

        # Ignore broadcasted messages ("i")
        if response_type == KebaResponse.BROADCAST:
            return

        waiting_key = (response_type, host)
        if response_type == KebaResponse.BASIC_INFO:
            waiting_key = (response_type, None)

        if receive_event := self._waiting_list.get(waiting_key, None):
            _LOGGER.debug("Received awaited response for (%s, %s)", response_type, host)
            receive_event.set()

            if response_type == KebaResponse.BASIC_INFO:
                # append data not override it
                data = self._waiting_response.get(waiting_key, [])
                data.append(host)

            self._waiting_response.update({waiting_key: data})
            return

        # Non waiting response -> push response to corresponding charging station
        if host not in self._charging_stations:
            _LOGGER.info(
                "Received a message from a not yet registered charging station at %s.",
                host,
            )
        else:
            charging_station = self._charging_stations.get(host)
            self._loop.create_task(charging_station.datagram_received(data))

    async def get_device_info(self, host: str) -> ChargingStationInfo:
        """Method to get device info for a charging station with given host

        Args:
            host (str): host or IP address to get device info from

        Raises:
            SetupError: Setup error will occure if timeout is reached

        Returns:
            ChargingStationInfo: charging stations device info
        """
        _LOGGER.debug("Schedule requesting device info from %s", host)

        # Add response listener
        waiting_key = (KebaResponse.REPORT_1, host)
        receive_event: asyncio.Event = asyncio.Event()
        self._waiting_list.update({waiting_key: receive_event})

        # Send and wait for positive response from host
        await self.send(host, "report 1")
        try:
            await asyncio.wait_for(receive_event.wait(), timeout=self._timeout)
        except asyncio.TimeoutError as exc:
            _LOGGER.warning(
                "Charging station at %s has not replied within %ds. Abort.",
                host,
                self._timeout,
            )
            raise SetupError("Could not get device info") from exc
        return ChargingStationInfo(
            host, json.loads(self._waiting_response.pop(waiting_key, None))
        )

    ####################################################
    #               Public Functions                   #
    ####################################################
    async def discover_devices(self, broadcast_addr: str) -> list[str]:
        """Method to start a discovery

        Args:
            broadcast_addr (str): IP Address to send discvoery message to,
                should be a network broadcast address

        Returns:
            List[str]: List of found hosts
        """
        _LOGGER.info(
            "Start discover of charging station by broadcasting to %s", broadcast_addr
        )

        # Add response listener and prepare response list
        waiting_key = (KebaResponse.BASIC_INFO, None)
        receive_event: asyncio.Event = asyncio.Event()
        self._waiting_list.update({waiting_key: receive_event})

        # Send and wait for positive response from host
        await self.send(broadcast_addr, "i")

        # As we do not know how many charging stations to find, wait for a the whole timeout period
        await asyncio.sleep(self._timeout)
        found_hosts = self._waiting_response.pop(waiting_key, [])
        _LOGGER.info("Found charging stations for %s: %s", broadcast_addr, found_hosts)
        return found_hosts

    async def setup_charging_station(self, host: str, **kwargs) -> ChargingStation:
        """Setup charging station into the connection handler

        Args:
            host (str): host of charging station to add to the connection handler

        Raises:
            SetupError: Setup error will occure if timeout is reached

        Returns:
            ChargingStation: charging station object to handle functions and readings
        """
        _LOGGER.info("Start setup of charging station at %s", host)

        # check if charging station is already configured
        if host in self._charging_stations:
            _LOGGER.info(
                "charging station at %s already configured. Return existing object.",
                host,
            )
            return self._charging_stations.get(host)

        # Get device info
        device_info_new: ChargingStationInfo = await self.get_device_info(host)

        # Check if charging station with same id (serial number) already exists
        for charging_station in self.get_charging_stations():
            if charging_station.device_info.device_id == device_info_new.device_id:
                _LOGGER.info(
                    "Found a charging station (Serial: %s %s) on a different IP address (%s). Updating device info.",
                    device_info_new.device_id,
                    charging_station.device_info.host,
                    device_info_new.host,
                )
                # update map key
                self._charging_stations[host] = self._charging_stations.pop(
                    charging_station.device_info.host
                )

                # upadte charging station device info
                charging_station.update_device_info(device_info_new)
                return charging_station

        # charging station not known, thus create a new instance for it
        charging_station = ChargingStation(self, device_info_new, self._loop, **kwargs)
        self._charging_stations.update({host: charging_station})

        _LOGGER.info(
            "%s charging station (Serial: %s) at %s successfully connected.",
            device_info_new.manufacturer,
            device_info_new.device_id,
            device_info_new.host,
        )
        return charging_station

    def remove_charging_station(self, host: str) -> None:
        """Remove charging station from the connection handler.

        Args:
            host (str): host of the charging station
        """
        if host in self._charging_stations:
            charging_station = self.get_charging_station(host)
            charging_station.stop_periodic_request()
            self._charging_stations.pop(host)
            _LOGGER.info("charging station at %s removed.", host)
        else:
            _LOGGER.warning(
                "charging station at %s could not be removed as it was not configured.",
                host,
            )

    def get_charging_stations(self):
        """Get a list of all configured charging stationes

        Returns:
            list(ChargingStation): list of charging station bjects
        """
        return list(self._charging_stations.values())

    def get_charging_station(self, host: str) -> ChargingStation:
        """Get a specific charging station by host

        Args:
            host (str): host of charging station to get

        Returns:
            ChargingStation: charging station object of given host
        """
        return self._charging_stations.get(host)

    async def send(self, host: str, payload: str, blocking_time: int = 0.1) -> None:
        """Send a payload to the charging station with given host

        Args:
            host (str): host of charging station to send payload to
            payload (str): raw payload to send encoded as cp437
            blocking_time (int): blocking time in seconds. Defaults to 100 ms.
        """

        if self._stream is None:
            _LOGGER.fatal("Cannot send data to the charging station. Setup failed.")
            return

        async with self._sending_lock:
            _LOGGER.debug("Send %s to %s", payload, host)

            await self._stream.send(payload.encode("cp437", "ignore"), (host, UDP_PORT))
            await asyncio.sleep(
                max(blocking_time, 0.1)
            )  # Sleep for blocking time but at least 100 ms


class SetupError(Exception):
    """Error to indicate we cannot connect."""


async def create_keba_connection(
    loop: asyncio.AbstractEventLoop | None = None,
    timeout: int = 3,
    bind_ip: str = "0.0.0.0",
) -> KebaKeContact:
    """Factory to get KebaKeContact object as keba connection handler

    Args:
        loop (asyncio.AbstractEventLoop | None, optional): asyncio loop. Defaults to None and thus retrieves the default loop.
        timeout (int, optional): common timeout to wait for reaction from the charging stations. Defaults to 3 seconds.
        bind_ip (str, optional): bind IP address. Defaults to "0.0.0.0".

    Returns:
        KebaKeContact: keba connection handler
    """
    loop = asyncio.get_event_loop() if loop is None else loop
    keba_connection = KebaKeContact(loop, timeout)
    await keba_connection.init_socket(bind_ip)
    return keba_connection
