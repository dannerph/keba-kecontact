from __future__ import annotations

from abc import ABC
import logging
import json
import string
import asyncio
import string
import datetime
import math

_LOGGER = logging.getLogger(__name__)


class WallboxDeviceInfo(ABC):
    def __init__(self, host, report_1_json) -> None:

        self.webconfigurl = f"http://{host}"
        self.host = host

        if report_1_json["ID"] != "1":
            _LOGGER.warning(
                "Device info extraction for new wallbox not possible. Got wrong report response."
            )
            return None
        try:
            self.device_id = report_1_json["Serial"]
            self.sw_version = report_1_json["Firmware"]

            self.manufacturer = "Unknown"

            product = report_1_json["Product"]
            self.model = product.split("-")[1:]

            # Friendly name mapping
            if "KC" in product:
                self.manufacturer = "KEBA"
                if "P30" in product:
                    self.model = "P30"
                if "P20" in product:
                    self.model = "P20"
            elif "BMW" in product:
                self.manufacturer = "BMW"
                if "BMW-10" in product:
                    self.model = "Wallbox Plus"

        except KeyError:
            _LOGGER.warning("Could not extract report 1 data for KEBA charging station")
            return None

    def __str__(self):
        return f"manufacturer: {self.manufacturer}\nmodel: {self.model}\ndevice_id (serial number): {self.device_id}\nfirmware version: {self.sw_version}\nhost: {self.host}"

    def available_services(self):
        services = [
            "set_failsafe",
            "request_data",
            "enable",
            "disable",
            "set_current",
            "unlock_socket",
            "set_charging_power",
        ]
        if "P30" in self.model:
            services.append("display")

        if "Keba" in self.manufacturer:
            services.append("set_output")

        if "BMW" in self.manufacturer or "P30" in self.model:
            services.append("set_energy")
            services.append("start")
            services.append("stop")
        return services


class Wallbox(ABC):
    def __init__(
        self,
        keba,
        device_info: WallboxDeviceInfo,
        loop=None,
        periodic_request: bool = True,
        refresh_interval: int = 5,
        refresh_interval_fast_polling: int = 1,
    ) -> None:
        """Initialize charging station connection."""
        # super().__init__(host, self.hass_callback)

        self._loop = asyncio.get_event_loop() if loop is None else loop

        self._keba = keba
        self.device_info = device_info
        self.data = dict()

        self._callbacks = []

        # Internal variables
        self._refresh_interval = refresh_interval
        self._refresh_interval_fast_polling = refresh_interval_fast_polling

        self._fast_polling_count_max = int(
            self._refresh_interval * 2 / self._refresh_interval_fast_polling
        )
        self._fast_polling_count = self._fast_polling_count_max

        self._polling_task = None
        self._periodic_request_enabled = periodic_request
        if self._periodic_request_enabled:
            self._polling_task = self._loop.create_task(self._periodic_request())

    def stop_periodic_request(self) -> None:
        if self._periodic_request:
            self._polling_task.cancel()
            _LOGGER.debug(
                f"Periodic requests for Wallbox {self.device_info.model} at {self.device_info.host} stopped."
            )

    def add_callback(self, callback) -> None:
        """Add callback function to be called after new data is received."""
        self._callbacks.append(callback)

    def get_value(self, key: str):
        """Get value. If key is None, all data is return, otherwise the respective value or if non existing none is returned."""
        if key is None:
            return self.data
        else:
            try:
                value = self.data[key]
                return value
            except KeyError:
                return None

    async def datagram_received(self, data):
        """Handle received datagram."""
        _LOGGER.debug("Datagram received, starting to process.")
        decoded_data = data.decode()

        if "TCH-OK :done" in decoded_data:
            _LOGGER.debug("Command accepted: %s", decoded_data.rstrip())
            return True

        if "TCH-ERR" in decoded_data:
            _LOGGER.warning("Command rejected: %s", decoded_data.rstrip())
            return False

        json_rcv = json.loads(data.decode())

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
            json_rcv["Plug_wallbox"] = plug_state > 0
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
        if "FS_on" in json_rcv:
            json_rcv["FS_on"] = json_rcv["Tmo FS"] > 0

        if "P" in json_rcv:
            json_rcv["P"] = round(json_rcv["P"] / 1000000.0, 2)

        self.data.update(json_rcv)

        # Join data to internal data store and send it to the callback function
        for callback in self._callbacks:
            callback(self, self.data)

        _LOGGER.debug("Executed %d callbacks", len(self._callbacks))

    ####################################################
    #            Data Polling Management               #
    ####################################################

    async def _send(self, payload: str, fast_polling: bool = False) -> None:
        await self._keba.send(self.device_info.host, payload)
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

        _LOGGER.debug("Periodic data request executed, now wait for %s seconds", sleep)
        await asyncio.sleep(sleep)

        self._polling_task = self._loop.create_task(self._periodic_request())
        _LOGGER.debug("Periodic data request rescheduled")

    ####################################################
    #                   Functions                      #
    ####################################################

    async def request_data(self, **kwargs) -> None:
        """Send request for KEBA charging station data.

        This function requests report 2, report 3 and report 100.
        """
        await self._send("report 2")
        await self._send("report 3")

        if "P20" not in self.device_info.model:
            await self._send("report 100")

    async def set_failsafe(
        self,
        timeout: int = 30,
        fallback_value: int = 6,
        persist: bool = False,
        **kwargs,
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

        await self._send(
            f"failsafe {timeout} {fallback_value * 1000} {1 if persist else 0}",
            fast_polling=True,
        )

    async def enable(self, **kwargs) -> None:
        """Start a charging process."""
        await self.set_ena(True)

    async def disable(self, **kwargs) -> None:
        """Stop a charging process."""
        await self.set_ena(False)

    async def set_ena(self, ena: bool, **kwargs) -> None:
        """Set ena."""
        if not isinstance(ena, bool):
            raise ValueError("Enable parameter must be True or False.")

        await self._send(f"ena {1 if ena else 0}", fast_polling=True)

    async def set_current(self, current: int | float, delay: int = 0, **kwargs) -> None:
        """Send command to set current limit on KEBA charging station.
        This function sets the current limit in A after a given delay in seconds. 0 A stops the charging process similar to ena 0.
        """
        if (
            not isinstance(current, (int, float))
            or (current < 6 and current != 0)
            or current >= 63
        ):
            raise ValueError(
                "Current must be int or float and value must be above 6 and below 63 A."
            )

        if not isinstance(delay, int) or delay < 0 or delay >= 860400:
            raise ValueError(
                "Delay must be int and value must be between 0 and 860400 seconds."
            )

        current_mA = int(round(current)) * 1000
        cmd = f"currtime {current_mA} {delay}" if delay > 0 else f"curr {current_mA}"
        await self._send(cmd, fast_polling=True)

    async def set_energy(self, energy: int | float = 0, **kwargs) -> None:
        """Send command to set energy limit on KEBA charging station.
        This function sets the energy limit in kWh. For deactivation energy should be 0.
        """
        if "P20" in self.device_info.model:
            raise NotImplementedError("set_energy is not available on the Keba P20.")

        if (
            not isinstance(energy, (int, float))
            or (energy < 1 and energy != 0)
            or energy >= 10000
        ):
            raise ValueError(
                "Energy must be int or float and value must be above 0.0001 kWh and below 10000 kWh."
            )

        await self._send(f"setenergy {int(round(energy * 10000))}", fast_polling=True)

    async def set_output(self, out: int, **kwargs) -> None:
        """Start a charging process."""
        if "BMW" in self.device_info.manufacturer:
            raise NotImplementedError("output is not available on the BMW Wallbox.")

        if not isinstance(out, int) or out < 0 or (out > 1 and out < 10) or out > 150:
            raise ValueError("Output parameter must be True or False.")

        await self._send(f"output {out}")

    async def start(
        self, rfid: str = None, rfid_class: str = "01010400000000000000", **kwargs
    ) -> None:  # Default color white
        """Authorize a charging process with given RFID tag."""
        if "P20" in self.device_info.model:
            raise NotImplementedError("start is not available on the Keba P20.")

        cmd = "start"
        if rfid is not None:
            if not all(c in string.hexdigits for c in rfid) or len(rfid) > 16:
                raise ValueError("RFID tag must be a 8 byte hex string.")
            if not all(c in string.hexdigits for c in rfid_class) or len(rfid) > 20:
                raise ValueError("RFID class tag must be a 10 byte hex string.")
            cmd = f"start {rfid} {rfid_class}"

        await self._send(cmd, fast_polling=True)

    async def stop(self, rfid: str = None, **kwargs) -> None:
        """De-authorize a charging process with given RFID tag."""
        if "P20" in self.device_info.model:
            raise NotImplementedError("stop is not available on the Keba P20.")

        cmd = "stop"
        if rfid is not None:
            if not all(c in string.hexdigits for c in rfid) or len(rfid) > 16:
                raise ValueError("RFID tag must be a 8 byte hex string.")
            cmd = f"stop {rfid}"

        await self._send(cmd, fast_polling=True)

    async def display(
        self, text: str, mintime: int | float = 2, maxtime: int | float = 10, **kwargs
    ) -> None:
        """Show a text on the display."""
        if "P30" not in self.device_info.model:
            raise NotImplementedError("display is only available on the Keba P30.")

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

    async def unlock_socket(self, **kwargs) -> None:
        """Unlock the socket.
        For this command you have to disable the charging process first. Afterwards you can unlock the socket.
        """
        await self._send("unlock")

    async def set_charging_power(
        self, power: int | float, round_up: bool = False, **kwargs
    ) -> bool:
        """Set chargig power in kW. EXPERIMENTAL!
        For this command you have to start a charging process first. Afterwards the charging power in kW can be adjusted. The given power is the maximum power, current values are rounded down to not overshoot this power value
        """

        # Abort if there is no active charging process
        if not self.get_value("State_on"):
            await self.set_ena(True)
            _LOGGER.warning(
                "Charging power can only be set during active charging process. Sent enable it (in case of active authentication)"
            )
            return False

        if not isinstance(power, (int, float)):
            raise ValueError("Power must be int or float.")

        if power < 0 or power > 44.0:
            raise ValueError("Power must be between 0 and 44 kW.")

        # Identify the number of phases that are used to charge and calculate average voltage of active phases
        number_of_phases = 0
        avg_voltage = 0.0
        MINIMUM_POWER = (
            2  # Watt to check if a charging process is running on the three phases
        )
        try:
            p1 = self.get_value("I1") * self.get_value("U1")
            p2 = self.get_value("I2") * self.get_value("U2")
            p3 = self.get_value("I3") * self.get_value("U3")
            _LOGGER.debug(
                f"set_charging_power phase 1 measurements: {p1}, {self.get_value('I1')}, {self.get_value('U1')}"
            )
            _LOGGER.debug(
                f"set_charging_power phase 2 measurements: {p2}, {self.get_value('I2')}, {self.get_value('U2')}"
            )
            _LOGGER.debug(
                f"set_charging_power phase 3 measurements: {p3}, {self.get_value('I3')}, {self.get_value('U3')}"
            )

            if p1 > MINIMUM_POWER:
                number_of_phases += 1
                avg_voltage += self.get_value("U1")
            if p2 > MINIMUM_POWER:
                number_of_phases += 1
                avg_voltage += self.get_value("U2")
            if p3 > MINIMUM_POWER:
                number_of_phases += 1
                avg_voltage += self.get_value("U3")

            avg_voltage = avg_voltage / number_of_phases

            _LOGGER.debug(
                f"set_charging_power number of phases: {number_of_phases} with average voltage of {avg_voltage}"
            )
        except:
            _LOGGER.error(
                "Unable to identify number of charging phases. Probably no measurement values received yet."
            )
            return False

        if number_of_phases == 0:
            _LOGGER.error("No charging process running.")
            return False

        # Calculate charging current
        current = 0
        if round_up:
            current = math.ceil((power * 1000.0) / avg_voltage / number_of_phases)
        else:
            current = (
                (power * 1000.0) / avg_voltage / number_of_phases
            )  # int cap = round down not to overshoot the maximum

        try:
            if current == 0:
                await self.set_ena(False)  # disable if charging power is 0 kW
            else:
                # Enable if disabled
                if (
                    self.get_value("Enable sys") == 0
                    or self.get_value("Enable user") == 0
                ):
                    await self.set_ena(True)

                if current < 6.0:
                    await self.set_current(current=6)
                elif current < 63:
                    await self.set_current(current=current)
                else:
                    _LOGGER.error(
                        f"Calculated current is much too high, something wrong"
                    )
        except ValueError as e:
            _LOGGER.error(f"Could not set calculated current {e}")

        return True
