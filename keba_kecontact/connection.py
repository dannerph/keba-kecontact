#!/usr/bin/python3

from keba_kecontact.keba_protocol import KebaProtocol
import asyncio
import string


class KebaKeContact:
    _UDP_IP = None
    _UDP_PORT = 7090
    _setup = False

    def __init__(self, ip, callback=None):
        """ Constructor. """
        self._UDP_IP = ip
        self._callback = callback
        self.keba_protocol = None

    def callback(self, data_json):
        if self._callback is not None:
            self._callback(data_json)

    def get_value(self, key):
        """Return wallbox value for given key if available, otherwise None."""
        try:
            value = self.keba_protocol.data[key]
            return value
        except KeyError:
            return None

    async def setup(self, loop=None):
        """Add datagram endpoint to asyncio loop."""
        loop = asyncio.get_event_loop() if loop is None else loop
        self.keba_protocol = KebaProtocol(self.callback)
        await loop.create_datagram_endpoint(lambda: self.keba_protocol,
                                            local_addr=('0.0.0.0', self._UDP_PORT),
                                            remote_addr=(self._UDP_IP, self._UDP_PORT))
        # Test connection to keba charging station
        self.keba_protocol.send("report 1")
        await asyncio.sleep(0.1)
        if self.get_value("Product") is None:
            raise ConnectionError('Could not connect to Keba charging station at ' + str(self._UDP_IP) + '.')
        
        self._setup = True

    async def request_data(self):
        """Send request for KEBA charging station data.

        This function requests report 1, report 2 and report 3.
        """
        if not self._setup:
            await self.setup()

        self.keba_protocol.send("report 1")
        await asyncio.sleep(0.1)  # Sleep for 100 ms as given in the manual
        self.keba_protocol.send("report 2")
        await asyncio.sleep(0.1)
        self.keba_protocol.send("report 3")
        await asyncio.sleep(0.1)

    async def set_failsafe(self, timeout=30, fallback_value=6, persist=0):
        """Send command to activate failsafe mode on KEBA charging station.

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

        self.keba_protocol.send('failsafe ' + str(timeout) + ' ' + str(fallback_value * 1000) + ' ' + str(persist))
        await asyncio.sleep(0.1)  # Sleep for 100ms as given in the manual

    async def set_energy(self, energy=0):
        """Send command to set energy limit on KEBA charging station.

        This function sets the energy limit in kWh. For deactivation energy should be 0.
        """
        if not self._setup:
            await self.setup()

        if not isinstance(energy, (int, float)) or (energy < 1 and energy != 0) or energy >= 10000:
            raise ValueError("Energy must be int or float and value must be above 0.0001 kWh and below 10000 kWh.")

        self.keba_protocol.send('setenergy ' + str(energy * 10000))
        await asyncio.sleep(0.1)  # Sleep for 100 ms as given in the manual

    async def set_current(self, current=0, *_):
        """Send command to set current limit on KEBA charging station.

        This function sets the current limit in A. 0 A stops the charging process similar to ena 0.
        """
        if not self._setup:
            await self.setup()

        if not isinstance(current, (int, float)) or (current < 6 and current != 0) or current >= 63:
            raise ValueError("Current must be int or float and value must be above 6 and below 63 A.")

        self.keba_protocol.send('currtime ' + str(current * 1000) + ' 1')
        await asyncio.sleep(0.1)  # Sleep for 100 ms as given in the manual

    async def set_text(self, text, mintime=2, maxtime=10):
        """Show a text on the display."""
        if not self._setup:
            await self.setup()

        if not isinstance(mintime, (int, float)) or not isinstance(maxtime, (int, float)):
            raise ValueError("Times must be int or float.")

        if mintime < 0 or mintime > 65535 or maxtime < 0 or maxtime > 65535:
            raise ValueError("Times must be between 0 and 65535")

        self.keba_protocol.send("display 1 " + str(int(round(mintime))) + ' ' + str(int(round(maxtime))) + " 0 " + text[0:23])
        await asyncio.sleep(0.1)  # Sleep for 100 ms as given in the manual

    async def start(self, rfid, rfid_class="01010400000000000000"):  # Default color white
        """Authorize a charging process with predefined RFID tag."""
        if not self._setup:
            await self.setup()

        if not all(c in string.hexdigits for c in rfid) or len(rfid) > 16:
            raise ValueError("RFID tag must be a 8 byte hex string.")

        if not all(c in string.hexdigits for c in rfid_class) or len(rfid) > 20:
            raise ValueError("RFID class tag must be a 10 byte hex string.")

        self.keba_protocol.send("start " + rfid + ' ' + rfid_class)
        await asyncio.sleep(0.1)  # Sleep for 100 ms as given in the manual

    async def stop(self, rfid):
        """De-authorize a charging process with predefined RFID tag."""
        if not self._setup:
            await self.setup()

        if not all(c in string.hexdigits for c in rfid) or len(rfid) > 16:
            raise ValueError("RFID tag must be a 8 byte hex string.")

        self.keba_protocol.send("stop " + rfid)
        await asyncio.sleep(0.1)  # Sleep for 100 ms as given in the manual

    async def enable(self, ena):
        """Start a charging process."""
        if not self._setup:
            await self.setup()

        if not isinstance(ena, bool):
            raise ValueError("Enable parameter must be True or False.")
        param_str = 1 if ena else 0
        self.keba_protocol.send("ena " + str(param_str))
        await asyncio.sleep(0.1)  # Sleep for 100 ms as given in the manual

    async def unlock_socket(self):
        """Unlock the socket.

        For this command you have to disable the charging process first. Afterwards you can unlock the socket.
        """
        if not self._setup:
            await self.setup()

        self.keba_protocol.send("unlock")
        await asyncio.sleep(0.1)  # Sleep for 100 ms as given in the manual
