"""Implementation of a Keba charging station"""

import asyncio
import datetime
import json
import logging
import math
import string
from enum import Enum
from typing import Any

from keba_kecontact.const import FIRMWARE, ID, PRODUCT, SERIAL, UNKNOWN

_LOGGER = logging.getLogger(__name__)


class KebaService(Enum):
    """Enum to represent implemented services to be used with a Keba charging station"""

    SET_FAILSAFE = "set_failsafe"
    SET_CURRENT = "set_current"
    SET_CHARIGNG_POWER = "set_charging_power"
    SET_ENERGY = "set_energy"
    SET_OUTPUT = "set_output"
    DISPLAY = "display"
    START = "start"
    STOP = "stop"


class ChargingStationInfo:
    """This class represents a Keba charging station information object. It is used to identify
    features and available services
    """

    def __init__(self, host: str, report_1_json) -> None:
        self.webconfigurl: str = f"http://{host}"
        self.host: str = host

        # Features
        self.services: list(KebaService) = [
            KebaService.SET_FAILSAFE,
            KebaService.SET_CURRENT,
            KebaService.SET_CHARIGNG_POWER,
        ]
        self.meter_integrated = False
        self.data_logger_integrated = False

        if report_1_json[ID] != "1":
            _LOGGER.warning(
                "Device info extraction for new charging station not possible. Got wrong report response."
            )
            return
        try:
            self.device_id: str = report_1_json[SERIAL]
            self.sw_version: str = report_1_json[FIRMWARE]

            product: str = report_1_json[PRODUCT]

            # Friendly name mapping
            if "KC" in product:
                self.manufacturer = "KEBA"
                self.services.append(KebaService.SET_OUTPUT)

                if "KC-P30-EC220112-000-DE" in product:
                    self.model = "P30-DE"
                    self.meter_integrated = False
                    self.data_logger_integrated = True
                elif "P30" in product:
                    self.model = "P30"

                    # Add available services
                    self.services.append(KebaService.DISPLAY)
                    self.services.append(KebaService.SET_ENERGY)
                    self.services.append(KebaService.START)
                    self.services.append(KebaService.STOP)

                    self.meter_integrated = True
                    self.data_logger_integrated = True

                elif "P20" in product:
                    self.model = "P20"
                    self.meter_integrated = False
                    self.data_logger_integrated = False

            elif "BMW" in product:
                self.manufacturer = "BMW"
                if "BMW-10-EC2405B2-E1R" in product:
                    self.model = "Wallbox Connect"
                elif "BMW-10-EC240522-E1R" in product:
                    self.model = "Wallbox Plus"

                # Add available services
                self.services.append(KebaService.SET_ENERGY)
                self.services.append(KebaService.START)
                self.services.append(KebaService.STOP)

                self.meter_integrated = True
                self.data_logger_integrated = True
            else:
                _LOGGER.warning(
                    "Not able to identify the model type. Please report to https://github.com/dannerph/keba-kecontact/issues"
                )
                self.manufacturer: str = UNKNOWN
                self.model = product.split("-")[1:]

        except KeyError:
            _LOGGER.warning("Could not extract report 1 data for KEBA charging station")
            return

    def available_services(self) -> list[str]:
        """Get available services as a list of method name strings

        Returns:
            list[str]: list of services
        """
        return self.services

    def is_meter_integrated(self) -> bool:
        """Method to check if a metering device is integrated into the charging station

        Returns:
            bool: True if metering is integrated, False otherwise
        """
        return self.meter_integrated

    def is_data_logger_integrated(self) -> bool:
        """Method to check if logging funcitonionality is integrated into the charging staiton

        Returns:
            bool: True if report 1XX is available, False otherwise
        """
        return self.data_logger_integrated

    def has_display(self) -> bool:
        """Method to check if a display is integrated into the charging staiton

        Returns:
            bool: True if a display is integrated, False otherwise
        """
        return KebaService.DISPLAY in self.services

    def __str__(self) -> str:
        return f"{self.manufacturer} {self.model} ({self.device_id} - {self.sw_version}) at {self.host}"


class ChargingStation:
    """This class represents a KEBA charging station (charging station)"""

    def __init__(
        self,
        keba,
        device_info: ChargingStationInfo,
        loop=None,
        periodic_request: bool = True,
        refresh_interval_s: int = 5,
        refresh_interval_fast_polling_s: int = 1,
    ) -> None:
        """Initialize charging station connection."""
        # super().__init__(host, self.hass_callback)

        self._loop = asyncio.get_event_loop() if loop is None else loop

        self._keba = keba
        self.device_info = device_info
        self.data = {}

        self._callbacks = []

        # Internal variables
        self._refresh_interval = max(refresh_interval_s, 5)  # at least 5 seconds
        self._refresh_interval_fast_polling = max(
            refresh_interval_fast_polling_s, 1
        )  # at least 1 second

        self._fast_polling_count_max = int(
            self._refresh_interval * 2 / self._refresh_interval_fast_polling
        )
        self._fast_polling_count = self._fast_polling_count_max

        self._polling_task = None
        self._periodic_request_enabled = periodic_request
        if self._periodic_request_enabled:
            self._polling_task = self._loop.create_task(self._periodic_request())

        self._charging_started_event: asyncio.Event = asyncio.Event()

    def update_device_info(self, device_info: ChargingStationInfo) -> None:
        """Updates the device info in the charging station object

        Args:
            device_info (ChargingStationInfo): new device info
        """
        # Stop periodic requests
        self.stop_periodic_request()

        # Exchange device info
        self.device_info = device_info

        # Start periodic requests if enabled
        if self._periodic_request_enabled:
            self._polling_task = self._loop.create_task(self._periodic_request())

    def stop_periodic_request(self) -> None:
        """This method stops the peridodic data reqeusts."""
        if self._polling_task is not None:
            self._polling_task.cancel()
            _LOGGER.debug(
                "Periodic requests for charging station %s at %s stopped.",
                self.device_info.model,
                self.device_info.host,
            )

    async def datagram_received(self, data) -> None:
        """Handle received datagram."""
        _LOGGER.info("%s datagram received", self.device_info)
        _LOGGER.debug("Data: %s", data.rstrip())

        if "TCH-OK :done" in data:
            _LOGGER.debug("Last command accepted: %s", data.rstrip())
            return

        if "TCH-ERR" in data:
            _LOGGER.warning("Last command rejected: %s", data.rstrip())
            return

        json_rcv = json.loads(data)

        # Try to edit json to more human-friendly formats
        if "Sec" in json_rcv:
            secs = json_rcv["Sec"]
            json_rcv["uptime_pretty"] = str(datetime.timedelta(seconds=secs))

        # Correct thousands
        thousands = json_rcv.keys() & [
            "Max curr %",
            "Max curr",
            "Curr HW",
            "Curr user",
            "Curr FS",
            "Curr timer",
            "I1",
            "I2",
            "I3",
            "PF",
        ]
        for k in thousands:
            json_rcv[k] = json_rcv[k] / 1000.0

        if "Max curr %" in json_rcv:
            json_rcv["Max curr %"] = json_rcv["Max curr %"] / 10.0

        # Correct ten-thousands, precision 2
        ten_thousands = json_rcv.keys() & ["Setenergy", "E pres", "E total", "E start"]
        for k in ten_thousands:
            json_rcv[k] = round(json_rcv[k] / 10000.0, 2)

        # Extract plug state
        if "Plug" in json_rcv:
            plug_state = int(json_rcv["Plug"])
            json_rcv["Plug_charging_station"] = plug_state > 0
            json_rcv["Plug_locked"] = plug_state == 3 | plug_state == 7
            json_rcv["Plug_EV"] = plug_state > 4

        # Extract charging state
        if "State" in json_rcv:
            state = int(json_rcv["State"])
            json_rcv["State_on"] = state == 3
            if state is not None:
                switcher = {
                    0: "starting",
                    1: "not ready for charging",
                    2: "ready for charging",
                    3: "charging",
                    4: "error",
                    5: "authorization rejected",
                }
                json_rcv["State_details"] = switcher.get(state, "State undefined")

        # Extract failsafe details
        if "Tmo FS" in json_rcv:
            json_rcv["FS_on"] = json_rcv["Tmo FS"] > 0

        if "P" in json_rcv:
            json_rcv["P"] = round(json_rcv["P"] / 1000000.0, 2)

        # Cleanup invalid values
        if "Curr HW" in json_rcv and json_rcv["Curr HW"] == 0:
            json_rcv.pop("Curr HW")

        self.data.update(json_rcv)

        # Join data to internal data store and send it to the callback function
        for callback in self._callbacks:
            callback(self, self.data)

        if int(self.get_value("State")) == 3 and ID in json_rcv and "3" in json_rcv[ID]:
            self._charging_started_event.set()

        _LOGGER.debug("Executed %d callbacks", len(self._callbacks))

    ####################################################
    #            Data Polling Management               #
    ####################################################

    async def _send(
        self, payload: str, fast_polling: bool = False, blocking_time_s: int = 0
    ) -> None:
        await self._keba.send(self.device_info.host, payload, blocking_time_s)
        if self._periodic_request_enabled and fast_polling:
            _LOGGER.debug("Fast polling enabled")
            self._fast_polling_count = 0
            self._polling_task.cancel()
            self._polling_task = self._loop.create_task(self._periodic_request())

    async def _periodic_request(self) -> None:
        """Send  periodic update requests."""

        if not self._periodic_request_enabled:
            _LOGGER.warning(
                "periodic request was not enabled at setup. This error should not appear."
            )
            return False

        await self.request_data()

        sleep = self._refresh_interval
        if self._fast_polling_count < self._fast_polling_count_max:
            self._fast_polling_count += 1
            sleep = self._refresh_interval_fast_polling

        _LOGGER.info("Periodic data request executed, now wait for %s seconds", sleep)
        await asyncio.sleep(sleep)

        self._polling_task = self._loop.create_task(self._periodic_request())
        _LOGGER.debug("Periodic data request rescheduled")

    ####################################################
    #                   Functions                      #
    ####################################################
    def add_callback(self, callback) -> None:
        """Add callback function to be called after new data is received."""
        self._callbacks.append(callback)

    def get_value(self, key: str) -> Any:
        """Get value. If key is None, all data is return, otherwise the respective value or if
        non-existing key none is returned."""
        if key is None:
            return self.data
        try:
            return self.data[key]
        except KeyError:
            return None

    async def request_data(
        self,
        **kwargs,  # pylint: disable=unused-argument
    ) -> None:
        """Send request for KEBA charging station data.

        This function requests report 2, report 3 and report 100.
        """
        await self._send("report 2")

        if self.device_info.is_meter_integrated():
            await self._send("report 3")

        if self.device_info.is_data_logger_integrated():
            await self._send("report 100")

    async def set_failsafe(
        self,
        mode: bool = True,
        timeout: int = 30,
        fallback_value: int = 6,
        persist: bool = False,
        **kwargs,  # pylint: disable=unused-argument
    ) -> None:
        """Send command to activate failsafe mode on KEBA charging station.
        This function sets the failsafe mode. For deactivation, all parameters must be 0.
        """
        if (timeout < 10 and timeout != 0) or timeout > 600:
            raise ValueError(
                "Failsafe timeout must be between 10 and 600 seconds or 0 for deactivation."
            )

        if (fallback_value < 6 and fallback_value != 0) or fallback_value > 63:
            raise ValueError(
                "Failsafe fallback value must be between 6 and 63 A or 0 to stop charging."
            )

        if not isinstance(persist, bool):
            raise ValueError("Failsafe persist must be True or False.")

        if not isinstance(mode, bool):
            raise ValueError("Failsafe mode must be True or False.")

        if mode:
            await self._send(
                f"failsafe {timeout} {fallback_value * 1000} {1 if persist else 0}",
                fast_polling=True,
            )
        else:
            await self._send(
                f"failsafe 0 0 {1 if persist else 0}",
                fast_polling=True,
            )

    async def enable(self, **kwargs) -> None:  # pylint: disable=unused-argument
        """Start a charging process."""
        await self.set_ena(True)

    async def disable(self, **kwargs) -> None:  # pylint: disable=unused-argument
        """Stop a charging process."""
        await self.set_ena(False)

    async def set_ena(
        self, ena: bool, **kwargs  # pylint: disable=unused-argument
    ) -> None:
        """Set ena."""
        if not isinstance(ena, bool):
            raise ValueError("Enable parameter must be True or False.")
        if ena:
            # enable
            await self._send(f"ena {1 if ena else 0}", fast_polling=True)
        else:
            # disable and block 2 seconds
            await self._send(
                f"ena {1 if ena else 0}", fast_polling=True, blocking_time_s=2
            )

    async def set_current_max_permanent(
        self,
        current: int | float,
        **kwargs,  # pylint: disable=unused-argument
    ) -> None:  # pylint: disable=unused-argument
        """Send command to set current limit on KEBA charging station.
        This function sets the current limit in A after a given delay in seconds. 0 A stops the charging process similar to ena 0.
        """
        if (
            not isinstance(current, (int, float))
            or (current < 6 and current != 0)
            or current > 63
        ):
            raise ValueError(
                "Current must be int or float and value must be above 6 and below 63 A."
            )

        current_mA = int(round(current * 1000))  # pylint: disable=invalid-name
        cmd = f"curr {current_mA}"
        await self._send(cmd, fast_polling=True)

    async def set_current(
        self,
        current: int | float,
        delay: int = 1,
        **kwargs,  # pylint: disable=unused-argument
    ) -> None:  # pylint: disable=unused-argument
        """Send command to set current limit on KEBA charging station.
        This function sets the current limit in A after a given delay in seconds. 0 A stops the charging process similar to ena 0.
        """
        if "P20" in self.device_info.model:
            _LOGGER.warning(
                "Keba P20 does not support currtime, using curr instead. Delays are neglected"
            )
            await self.set_current_max_permanent(current)
        if (
            not isinstance(current, (int, float))
            or (current < 6 and current != 0)
            or current > 63
        ):
            raise ValueError(
                "Current must be int or float and value must be above 6 and below 63 A."
            )

        if not isinstance(delay, int) or delay < 0 or delay >= 860400:
            raise ValueError(
                "Delay must be int and value must be between 0 and 860400 seconds."
            )

        current_mA = int(round(current * 1000))  # pylint: disable=invalid-name
        cmd = f"currtime {current_mA} {delay}"
        await self._send(cmd, fast_polling=True)

    async def set_energy(
        self, energy: int | float = 0, **kwargs  # pylint: disable=unused-argument
    ) -> None:
        """Send command to set energy limit on KEBA charging station.
        This function sets the energy limit in kWh. For deactivation energy should be 0.
        """
        if KebaService.SET_ENERGY not in self.device_info.services:
            raise NotImplementedError(
                "set_energy is not available for the given charging station."
            )

        if (
            not isinstance(energy, (int, float))
            or (energy < 1 and energy != 0)
            or energy >= 10000
        ):
            raise ValueError(
                "Energy must be int or float and value must be above 0.0001 kWh and below 10000 kWh."
            )

        await self._send(f"setenergy {int(round(energy * 10000))}", fast_polling=True)

    async def set_output(
        self, out: int, **kwargs  # pylint: disable=unused-argument
    ) -> None:
        """Start a charging process."""
        if KebaService.SET_OUTPUT not in self.device_info.services:
            raise NotImplementedError(
                "set_output is not available for the given charging station."
            )

        if not isinstance(out, int) or out < 0 or (out > 1 and out < 10) or out > 150:
            raise ValueError("Output parameter must be True or False.")

        await self._send(f"output {out}")

    async def start(
        self,
        rfid: str = None,
        rfid_class: str = "01010400000000000000",
        **kwargs,  # pylint: disable=unused-argument
    ) -> None:
        """Authorize a charging process with given RFID tag. Default rfid calss is color white"""
        if KebaService.START not in self.device_info.services:
            raise NotImplementedError(
                "start is not available for the given charging station."
            )

        cmd = "start"
        if rfid is not None:
            if not all(c in string.hexdigits for c in rfid) or len(rfid) > 16:
                raise ValueError("RFID tag must be a 8 byte hex string.")
            if not all(c in string.hexdigits for c in rfid_class) or len(rfid) > 20:
                raise ValueError("RFID class tag must be a 10 byte hex string.")
            cmd = f"start {rfid} {rfid_class}"

        await self.set_ena(True)
        await self._send(cmd, fast_polling=True, blocking_time_s=1)

    async def stop(
        self, rfid: str = None, **kwargs  # pylint: disable=unused-argument
    ) -> None:
        """De-authorize a charging process with given RFID tag."""
        if KebaService.STOP not in self.device_info.services:
            raise NotImplementedError(
                "stop is not available for the given charging station."
            )

        cmd = "stop"
        if rfid is not None:
            if not all(c in string.hexdigits for c in rfid) or len(rfid) > 16:
                raise ValueError("RFID tag must be a 8 byte hex string.")
            cmd = f"stop {rfid}"

        await self._send(cmd, fast_polling=True, blocking_time_s=1)

    async def display(
        self,
        text: str,
        mintime: int | float = 2,
        maxtime: int | float = 10,
        **kwargs,  # pylint: disable=unused-argument
    ) -> None:
        """Show a text on the display."""
        if KebaService.DISPLAY not in self.device_info.services:
            raise NotImplementedError(
                "display is not available for the given charging station."
            )

        if not isinstance(mintime, (int, float)) or not isinstance(
            maxtime, (int, float)
        ):
            raise ValueError("Times must be int or float.")

        if mintime < 0 or mintime > 65535 or maxtime < 0 or maxtime > 65535:
            raise ValueError("Times must be between 0 and 65535")

        # Formating
        text = text.replace(" ", "$")  # Will be translated back by the display

        await self._send(
            f"display 1 {int(round(mintime))} {int(round(maxtime))} 0 {text[0:23]}"
        )

    async def unlock_socket(self, **kwargs) -> None:  # pylint: disable=unused-argument
        """Unlock the socket.
        For this command you have to disable the charging process first. Afterwards you can unlock the socket.
        """
        await self._send("unlock")

    async def set_charging_power(
        self,
        power: int | float,
        round_up: bool = False,
        stop_below_6_A: bool = True,  # pylint: disable=invalid-name
        **kwargs,
    ) -> bool:
        """Set charging power in kW.
        For this command you have to authorize a charging process first. Afterwards the charging power in kW can be adjusted. The given power is the maximum power, current values are rounded down by default to not overshoot this power value.
        """
        if not self.device_info.is_meter_integrated():
            raise NotImplementedError(
                "set_charging_power only available in charging stations with integrated meter."
            )

        if not isinstance(power, (int, float)):
            raise ValueError("Power must be int or float.")

        if power < 0 or power > 44.0:
            raise ValueError("Power must be between 0 and 44 kW.")

        # Abort if there is no authorized charging process
        if self.get_value("Authreq") == 1:
            _LOGGER.warning(
                "Charging station is not authorized. Please authorize first, then run set_charging_power again."
            )
            return False

        if not self.get_value("State_on"):
            _LOGGER.info(
                "Charging process is authorized but stopped. The function now tries to enable it and waits for its start."
            )
            self._charging_started_event.clear()
            await self.set_ena(True)
            try:
                await asyncio.wait_for(self._charging_started_event.wait(), timeout=10)
            except asyncio.TimeoutError:
                _LOGGER.warning(
                    "Charging process could not be started after 10 seconds. Abort."
                )
                return False

        # Identify the number of phases that are used to charge and calculate average voltage of active phases
        number_of_phases = 0
        avg_voltage = 0.0
        try:
            p1 = self.get_value("I1") * self.get_value("U1")
            p2 = self.get_value("I2") * self.get_value("U2")
            p3 = self.get_value("I3") * self.get_value("U3")
            _LOGGER.debug(
                "set_charging_power measurements:\n"
                + "phase 1: %d, %d, %d \n"
                + "phase 2: %d, %d, %d \n"
                + "phase 3: %d, %d, %d",
                p1,
                self.get_value("I1"),
                self.get_value("U1"),
                p2,
                self.get_value("I2"),
                self.get_value("U2"),
                p3,
                self.get_value("I3"),
                self.get_value("U3"),
            )

            MINIMUM_POWER = 2
            if p1 > MINIMUM_POWER:
                number_of_phases += 1
                avg_voltage += self.get_value("U1")
            if p2 > MINIMUM_POWER:
                number_of_phases += 1
                avg_voltage += self.get_value("U2")
            if p3 > MINIMUM_POWER:
                number_of_phases += 1
                avg_voltage += self.get_value("U3")

            if number_of_phases == 0:
                _LOGGER.error("No charging process running.")
                return False

            avg_voltage = avg_voltage / number_of_phases

            _LOGGER.debug(
                "set_charging_power number of phases: %d with average voltage of %d",
                number_of_phases,
                avg_voltage,
            )
        except ValueError:
            _LOGGER.error(
                "Unable to identify number of charging phases. Probably no measurement values received yet."
            )
            return False

        # Calculate charging current
        current = 0
        current = (power * 1000.0) / avg_voltage / number_of_phases
        current = (
            math.ceil(current) if round_up else int(current)
        )  # int cap = round down not to overshoot the maximum

        try:
            if current == 0:
                await self.set_ena(False)  # disable if charging power is 0 kW
            else:
                # Enable if disabled
                if self.get_value("Enable user") == 0:
                    await self.set_ena(True)

                if current < 6.0:
                    if stop_below_6_A:
                        await self.set_ena(False)
                    else:
                        await self.set_current(current=6, delay=1)
                elif current < 63:
                    await self.set_current(current=current, delay=1)
                else:
                    _LOGGER.error(
                        "Calculated current is much too high, something wrong"
                    )
                    return False
        except ValueError:
            _LOGGER.error("Could not set calculated current.")

        return True
