#!/usr/bin/python3
from keba_kecontact.wallbox import Wallbox, WallboxDeviceInfo
import asyncio
import asyncio_dgram
import logging
import json

_LOGGER = logging.getLogger(__name__)

UDP_PORT = 7090


class KebaKeContact:
    def __init__(self, loop):
        """Constructor."""
        self._loop = loop = asyncio.get_event_loop() if loop is None else loop
        self._stream = None
        self._wallbox_map = dict()
        self._setup_event = None
        self._setup_info = None

        self._send_lock = asyncio.Lock()

    async def setup_wallbox(self, host, **kwargs):

        # Bind socket and start listening if not yet done
        if self._stream is None:
            self._stream = await asyncio_dgram.bind(("0.0.0.0", UDP_PORT))
            self._loop.create_task(self._listen())
            _LOGGER.debug("Socket binding created and listerning started.")

        # check if wallbox is already configured
        if host in self._wallbox_map:
            _LOGGER.warning("Given wallbox already configured. Abort.")
            return False

        # Test connection to new wallbox
        self._setup_event = asyncio.Event()
        await self._stream.send("report 1".encode("cp437", "ignore"), (host, UDP_PORT))
        await asyncio.sleep(0.1)

        # Wait for positive response from wallbox
        try:
            await asyncio.wait_for(self._setup_event.wait(), timeout=30)
            self._setup_event = None
        except asyncio.TimeoutError:
            _LOGGER.warning("Given wallbox has not replied within 30s. Abort.")
            return False

        # Create wallbox object and add it to observing map
        wb = Wallbox(keba=self, device_info=self._setup_info, loop=self._loop, **kwargs)
        self._setup_info = None

        self._wallbox_map.update({host: wb})
        _LOGGER.info(f"{wb.device_info.manufacturer} Wallbox (Serial: {wb.device_info.device_id}) at {wb.device_info.host} successfully connected.")
        return wb

    async def _listen(self):
        data, remote_addr = await self._stream.recv()  # Listen until something received
        self._loop.create_task(self._listen())  # Listen again
        self._loop.create_task(self._internal_callback(data, remote_addr))  # Callback

    async def _internal_callback(self, data, remote_addr):
        _LOGGER.debug(f"Datagram recvied from {remote_addr}: {data.decode()!r}")

        if remote_addr[0] not in self._wallbox_map:
            _LOGGER.debug("Received something from a not yet configured wallbox.")
            if self._setup_event is None:
                _LOGGER.debug(
                    "Data from new wallbox received but no configuration process running."
                )
            else:
                self._setup_info = self._create_device_info(remote_addr[0], data)
                self._setup_event.set()
        else:
            wb = self._wallbox_map.get(remote_addr[0])
            self._loop.create_task(wb.datagram_received(data))

    async def send(self, wallbox: Wallbox, payload):

        if (
            self._stream is None
            or wallbox.device_info.host not in self._wallbox_map.keys()
        ):
            raise ConnectionError("Setup the wallbox before sending.")

        _LOGGER.debug("Send %s to %s", payload, wallbox.device_info.host)

        async with self._send_lock:
            await self._stream.send(
                payload.encode("cp437", "ignore"), (wallbox.device_info.host, UDP_PORT)
            )
            await asyncio.sleep(0.1)  # Sleep for 100ms as given in the manual

    def _create_device_info(self, host, raw_data):
        json_rcv = json.loads(raw_data.decode())

        if json_rcv["ID"] != "1":
            _LOGGER.warning(
                "Device info extraction for new wallbox not possible. Got wrong response."
            )
            return None
        try:
            device_id = json_rcv["Serial"]
            model = json_rcv["Product"]
            sw_version = json_rcv["Firmware"]
            if "P30" in model or "P20" in model:
                manufacturer = "KEBA"
            elif "BMW" in model:
                manufacturer = "BMW"
            else:
                manufacturer = "Unkown"
        except KeyError:
            _LOGGER.warning("Could not extract report 1 data for KEBA charging station")
            return None
        return WallboxDeviceInfo(host, device_id, manufacturer, model, sw_version)
