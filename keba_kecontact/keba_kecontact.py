#!/usr/bin/python3

from keba_protocol import KebaProtocol
import asyncio
import logging
import string

_LOGGER = logging.getLogger(__name__)


class KebaKeContact:
    _UDP_IP = None
    _UDP_PORT = 7090
    _setup = False

    def __init__(self, ip, callback):
        """ Constructor. """
        self._UDP_IP = ip
        self._callback = callback

    async def setup(self):
        """Add datagram endpoint to asyncio loop."""
        loop = asyncio.get_running_loop()
        self.keba = KebaProtocol(self._callback)
        await loop.create_datagram_endpoint(lambda: self.keba,
                                            local_addr=('0.0.0.0', self._UDP_PORT),
                                            remote_addr=(self._UDP_IP, self._UDP_PORT))
        self._setup = True

    async def request_data(self):
        """Send request for KEBA charging station data.

        This function requests report 1, report 2 and report 3.
        """
        if not self._setup:
            await self.setup()

        await self.keba.send("report 1")
        await asyncio.sleep(0.1)  # Sleep for 100ms as given in the manual
        await self.keba.send("report 2")
        await asyncio.sleep(0.1)
        await self.keba.send("report 3")
        await asyncio.sleep(0.1)

    async def set_failsafe(self, timeout=30, fallback_value=6, persist=0):
        """Send command to activate failsave mode on KEBA charging station.

        This function sets the failsafe mode. For deactivation, all parameters must be 0.
        """
        if not self._setup:
            await self.setup()

        if (timeout < 10 and timeout != 0) or timeout > 600:
            raise ValueError("Failsafe timeout must be between 10 and 600 seconds or 0 for deactivation.")

        if (fallback_value < 6 and fallback_value != 0) \
                or fallback_value > 63:
            raise ValueError("Failsafe fallback value must be between 6 and 63 A or 0 to stop charging.")

        if persist not in [0, 1]:
            raise ValueError("Failsafe persist must be 0 or 1.")

        await self.keba.send('failsafe ' + str(timeout) + ' ' + str(fallback_value * 1000) + ' ' + str(persist))
        await asyncio.sleep(0.1)  # Sleep for 100ms as given in the manual

    async def set_energy(self, energy=0):
        """Send command to set energy limit on KEBA charging station.

        This function sets the energy limit in kWh. For deactivation energy should be 0.
        """
        if not self._setup:
            await self.setup()

        if (energy < 1 and energy != 0) or energy >= 10000:
            raise ValueError("Energy must be above 1 and below 10000 kWh.")

        await self.keba.send('setenergy ' + str(energy * 10000))
        await asyncio.sleep(0.1)  # Sleep for 100ms as given in the manual

    async def set_current(self, current=0):
        """Send command to set current limi on KEBA charging station.

        This function sets the current limit in A. 0 A stops the charging process similar to ena 0.
        """
        if not self._setup:
            await self.setup()

        if (current < 6 and current != 0) or current >= 63:
            raise ValueError("Current must be above 6 and below 63 A.")

        await self.keba.send('currtime ' + str(current * 1000) + ' 0')
        await asyncio.sleep(0.1)  # Sleep for 100ms as given in the manual

    async def start(self, rfid, rfid_class="01010400000000000000"):  # Default color white
        """Authorize a charging process with predefined RFID tag."""
        if not all(c in string.hexdigits for c in rfid) or len(rfid) > 16:
            raise ValueError("RFID tag must be a 8 byte hex string.")

        if not all(c in string.hexdigits for c in rfid_class) or len(rfid) > 20:
            raise ValueError("RFID class tag must be a 10 byte hex string.")

        self.send("start " + rfid + ' ' + rfid_class)

    async def stop(self, rfid):
        """Deauthorize a charging process with predefined RFID tag."""
        if not all(c in string.hexdigits for c in rfid) or len(rfid) > 16:
            raise ValueError("RFID tag must be a 8 byte hex string.")

        self.send("stop " + rfid)

    async def enable(self, ena):
        """Start a charging process."""
        if ena not in [0,1]:
            raise ValueError("Enable parameter must be 0 or 1.")
        self.send("ena " + str(ena))

    async def unlock_socket(self):
        """Unlock the socket.

        For this command you have to disable the charging process first. Afterwards you can unlock the socket.
        """
        self.send("unlock")
