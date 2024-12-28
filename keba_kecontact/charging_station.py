"""Keba charging station."""

import asyncio
import datetime
import json
import logging
import math
from typing import Any

from .charging_station_info import ChargingStationInfo
from .const import KebaResponse, KebaService, ReportField
from .utils import validate_current, validate_rfid_class, validate_rfid_tag

_LOGGER = logging.getLogger(__name__)


class ChargingStation:
    """KEBA charging station."""

    def __init__(
        self,
        keba_connection,
        device_info: ChargingStationInfo,
        loop: asyncio.AbstractEventLoop,
        periodic_request: bool = True,
        refresh_interval_s: int = 5,
        refresh_interval_fast_polling_s: int = 1,
    ) -> None:
        """Initialize charging station connection."""
        self._loop = loop

        self._keba = keba_connection
        self.device_info = device_info
        self.data = {}

        self._callbacks = []

        # Internal variables
        self._interval = max(refresh_interval_s, 5)  # at least 5 seconds
        self._interval_fast = max(refresh_interval_fast_polling_s, 1)  # at least 1 second

        self._fast_count_max = int(self._interval * 2 / self._interval_fast)
        self._fast_count = self._fast_count_max

        self._polling_task = None
        self._periodic_enabled = periodic_request
        if self._periodic_enabled:
            self._polling_task = self._loop.create_task(self._periodic_request())

        self._charging_started_event: asyncio.Event = asyncio.Event()

    def __eq__(self, other: Any) -> bool:  # noqa: ANN401
        """Equal if device_info is equal."""
        if isinstance(other, ChargingStation):
            return self.device_info == other.device_info
        return False

    def update_device_info(self, device_info: ChargingStationInfo) -> None:
        """Update device info in the charging station object.

        Args:
            device_info (ChargingStationInfo): new device info

        """
        self.stop_periodic_request()
        self.device_info = device_info
        if self._periodic_enabled:
            self._polling_task = self._loop.create_task(self._periodic_request())

    def stop_periodic_request(self) -> None:
        """Stop the periodic data requests."""
        if self._polling_task is not None:
            self._polling_task.cancel()
            _LOGGER.debug(
                "Periodic requests for charging station %s at %s stopped",
                self.device_info.model,
                self.device_info.host,
            )

    async def datagram_received(self, data: str) -> None:  # noqa: PLR0912
        """Handle received datagram.

        Args:
            data (str): payload of datagram

        """
        _LOGGER.debug("%s datagram received", self.device_info)
        _LOGGER.debug("Data: %s", data.rstrip())

        if KebaResponse.TCH_OK in data:
            _LOGGER.debug("Last command accepted: %s", data.rstrip())
            return

        if KebaResponse.TCH_ERR in data:
            _LOGGER.warning("Last command rejected: %s", data.rstrip())
            return

        json_rcv = json.loads(data)

        # Try to edit json to more human-friendly formats
        if "Sec" in json_rcv:
            secs = json_rcv["Sec"]
            json_rcv["uptime_pretty"] = str(datetime.timedelta(seconds=secs))

        # Correct thousands
        thousands = json_rcv.keys() & [
            ReportField.MAX_CURR_PERCENT,
            ReportField.MAX_CURR,
            ReportField.CURR_HW,
            ReportField.CURR_USER,
            ReportField.CURR_FS,
            ReportField.CURR_TIMER,
            ReportField.I1,
            ReportField.I2,
            ReportField.I3,
            ReportField.PF,
        ]
        for k in thousands:
            json_rcv[k] = json_rcv[k] / 1000.0

        if ReportField.MAX_CURR_PERCENT in json_rcv:
            json_rcv[ReportField.MAX_CURR_PERCENT] = json_rcv[ReportField.MAX_CURR_PERCENT] / 10.0

        # Correct ten-thousands, precision 2
        ten_thousands = json_rcv.keys() & [
            ReportField.SETENERGY,
            ReportField.E_PRES,
            ReportField.E_TOTAL,
            ReportField.E_START,
        ]
        for k in ten_thousands:
            json_rcv[k] = round(json_rcv[k] / 10000.0, 2)

        # Extract plug state
        if ReportField.PLUG in json_rcv:
            plug_state = int(json_rcv[ReportField.PLUG])
            json_rcv[ReportField.PLUG_CS] = plug_state > 0
            json_rcv[ReportField.PLUG_LOCKED] = plug_state == 3 | plug_state == 7
            json_rcv[ReportField.PLUG_EV] = plug_state > 4

        # Extract charging state
        if ReportField.STATE in json_rcv:
            state = int(json_rcv[ReportField.STATE])
            json_rcv[ReportField.STATE_ON] = state == 3
            if state is not None:
                switcher = {
                    0: "starting",
                    1: "not ready for charging",
                    2: "ready for charging",
                    3: "charging",
                    4: "error",
                    5: "authorization rejected",
                }
                json_rcv[ReportField.STATE_DETAILS] = switcher.get(state, "State undefined")

        # Extract failsafe details
        if ReportField.TMO_FS in json_rcv:
            json_rcv[ReportField.FS_ON] = json_rcv[ReportField.TMO_FS] > 0

        if ReportField.P in json_rcv:
            json_rcv[ReportField.P] = round(json_rcv[ReportField.P] / 1000000.0, 2)

        # Cleanup invalid values
        if ReportField.CURR_HW in json_rcv and json_rcv[ReportField.CURR_HW] == 0:
            json_rcv.pop(ReportField.CURR_HW)

        self.data.update(json_rcv)

        # Join data to internal data store and send it to the callback function
        for callback in self._callbacks:
            callback(self, self.data)

        if (
            int(self.get_value(ReportField.STATE)) == 3
            and ReportField.ID in json_rcv
            and "3" in json_rcv[ReportField.ID]
        ):
            self._charging_started_event.set()

        _LOGGER.debug("Executed %d callbacks", len(self._callbacks))

    ####################################################
    #            Data Polling Management               #
    ####################################################

    async def _send(
        self, payload: str, fast_polling: bool = False, blocking_time_s: int = 0
    ) -> None:
        await self._keba.send(self.device_info.host, payload, blocking_time_s)
        if self._periodic_enabled and fast_polling:
            _LOGGER.debug("Fast polling enabled")
            self._fast_count = 0
            self._polling_task.cancel()
            self._polling_task = self._loop.create_task(self._periodic_request())

    async def _periodic_request(self) -> None:
        """Send periodic update requests."""
        if not self._periodic_enabled:
            _LOGGER.warning("Periodic request was not enabled at setup")
            return False

        await self.request_data()

        sleep = self._interval
        if self._fast_count < self._fast_count_max:
            self._fast_count += 1
            sleep = self._interval_fast

        _LOGGER.debug("Periodic data request executed, now wait for %s seconds", sleep)
        await asyncio.sleep(sleep)

        self._polling_task = self._loop.create_task(self._periodic_request())
        _LOGGER.debug("Periodic data request rescheduled")

    ####################################################
    #                   Functions                      #
    ####################################################
    def add_callback(self, callback) -> None:
        """Add callback function to be called after new data is received."""
        self._callbacks.append(callback)

    def get_value(self, key: str | None = None) -> str | None:
        """Get value from internal data state.

        Args:
            key (str): key to fetch data for

        Returns:
            str | None: If key is None, all data is return, otherwise the respective value or if
        non-existing key None is returned.

        """
        if key is None:
            return self.data
        try:
            return self.data[key]
        except KeyError:
            return None

    async def request_data(self) -> None:
        """Send report 2, report 3 and report 100 requests."""
        await self._send("report 2")

        if self.device_info.is_meter_integrated():
            await self._send("report 3")

        if self.device_info.is_data_logger_integrated():
            await self._send("report 100")

    async def set_failsafe(
        self,
        mode: bool = True,
        timeout: int = 30,
        fallback_value: int | float = 6.0,
        persist: bool = False,
    ) -> None:
        """Activate failsafe mode, for deactivation all parameters must be 0.

        Args:
            mode (bool, optional): _description_. Defaults to True.
            timeout (int, optional): _description_. Defaults to 30.
            fallback_value (int | float, optional): _description_. Defaults to 6.
            persist (bool, optional): _description_. Defaults to False.

        """
        if (timeout < 10 and timeout != 0) or timeout > 600:
            raise ValueError(
                "Failsafe timeout must be between 10 and 600 seconds or 0 for deactivation."
            )
        validate_current(fallback_value)

        if not isinstance(persist, bool):
            raise ValueError("Failsafe persist must be True or False.")

        if not isinstance(mode, bool):
            raise ValueError("Failsafe mode must be True or False.")

        if mode:
            await self._send(
                f"failsafe {timeout} {int(round(fallback_value * 1000))} {1 if persist else 0}",
                fast_polling=True,
            )
        else:
            await self._send(f"failsafe 0 0 {1 if persist else 0}", fast_polling=True)

    async def enable(self) -> None:
        """Start a charging process."""
        await self.set_ena(True)

    async def disable(self) -> None:
        """Stop a charging process."""
        await self.set_ena(False)

    async def set_ena(self, ena: bool) -> None:
        """Set ena.

        Args:
            ena (bool): wether to enable or disable

        """
        if not isinstance(ena, bool):
            raise ValueError("Enable parameter must be True or False.")
        if ena:
            await self._send("ena 1", fast_polling=True)
        else:
            await self._send("ena 0", fast_polling=True, blocking_time_s=2)

    async def set_current_max_permanent(self, current: int | float) -> None:
        """Set current limit.

        Args:
            current (int | float): current limit in Ampere, valid range: 0 or between 6 - 63 A.
                0 stops the charging process like ena 0.

        """
        validate_current(current)
        cmd = f"curr {int(round(current * 1000))}"
        await self._send(cmd, fast_polling=True)

    async def set_current(self, current: int | float, delay: int = 1) -> None:
        """Set current limit.

        Args:
            current (int | float): current limit in Ampere, valid range: 0 or between 6 - 63 A.
                0 stops the charging process like ena 0.
            delay (int, optional): delay in seconds. Defaults to 1.

        """
        if "P20" in self.device_info.model:
            _LOGGER.warning("Keba P20 does not support currtime, delays are neglected")
            await self.set_current_max_permanent(current)

        validate_current(current)
        if not isinstance(delay, int) or delay < 0 or delay >= 860400:
            raise ValueError("Delay must be int and value must be between 0 and 860400 seconds.")

        cmd = f"currtime {int(round(current * 1000))} {delay}"
        await self._send(cmd, fast_polling=True)

    async def set_energy(self, energy: int | float = 0) -> None:
        """Set energy limit.

        Args:
            energy (int | float, optional): energy limit in kWh, 0 for deactivation. Defaults to 0.

        """
        if KebaService.SET_ENERGY not in self.device_info.services:
            raise NotImplementedError("set_energy is not available for the given charging station")

        if not isinstance(energy, int | float) or (energy < 1 and energy != 0) or energy >= 10000:
            raise ValueError(
                "Energy must be int or float and value must be above 0.0001 kWh and below 10000 kWh"
            )

        await self._send(f"setenergy {int(round(energy * 10000))}", fast_polling=True)

    async def set_output(self, out: int) -> None:
        """Set output.

        Args:
            out (int): value to set on output (1,0 or pulses/kWh from 10 up to 150)

        """
        if KebaService.SET_OUTPUT not in self.device_info.services:
            raise NotImplementedError("set_output is not available for the given charging station.")

        if not isinstance(out, int) or out < 0 or (out > 1 and out < 10) or out > 150:
            raise ValueError("Output parameter must be 1, 0, or pulses/kWh 10 - 150")

        await self._send(f"output {out}")

    async def start(
        self, rfid: str | None = None, rfid_class: str = "01010400000000000000"
    ) -> None:
        """Authorize a charging process with given RFID tag.

        Args:
            rfid (str | None, optional): RFID tag to authorize. Defaults to None.
            rfid_class (str, optional): RFID class/color. Defaults to "01010400000000000000".

        """
        if KebaService.START not in self.device_info.services:
            raise NotImplementedError("Start is not available for the given charging station")

        cmd = "start"
        if rfid is not None:
            validate_rfid_tag(rfid)
            validate_rfid_class(rfid_class)
            cmd = f"start {rfid} {rfid_class}"

        await self.set_ena(True)
        await self._send(cmd, fast_polling=True, blocking_time_s=1)

    async def stop(self, rfid: str | None = None) -> None:
        """De-authorize a charging process with given RFID tag.

        Args:
            rfid (str | None, optional): RFID tag to authorize. Defaults to None.

        """
        if KebaService.STOP not in self.device_info.services:
            raise NotImplementedError("Stop is not available for the given charging station")

        cmd = "stop"
        if rfid is not None:
            validate_rfid_tag(rfid)
            cmd = f"stop {rfid}"

        await self._send(cmd, fast_polling=True, blocking_time_s=1)

    async def display(self, text: str, mintime: int | float = 2, maxtime: int | float = 10) -> None:
        """Show a text on the display."""
        if KebaService.DISPLAY not in self.device_info.services:
            raise NotImplementedError("display is not available for the given charging station.")

        if not isinstance(mintime, int | float) or not isinstance(maxtime, int | float):
            raise ValueError("Times must be int or float.")

        if mintime < 0 or mintime > 65535 or maxtime < 0 or maxtime > 65535:
            raise ValueError("Times must be between 0 and 65535")

        # Format space
        text = text.replace(" ", "$")

        await self._send(f"display 1 {int(round(mintime))} {int(round(maxtime))} 0 {text[0:23]}")

    async def unlock_socket(self) -> None:
        """Unlock the socket.

        For this command you have to disable the charging process first. Afterwards you can unlock
        the socket.

        """
        await self._send("unlock")

    async def x2src(self, source: int) -> None:
        """Set x2src source.

        Args:
            source (int): Source for X2 output switching
                0 No phase toggle source is available
                1 Toggle via OCPP
                2 Direct toggle command via RESTAPI
                3 Toggle via Modbus
                4 Toggle via UDP

        """
        if not self.device_info.phase_switch_x2:
            raise NotImplementedError("x2 is not available for the given charging station")

        if not isinstance(source, int) and source >= 0 and source <= 4:
            raise ValueError("Source must be between 0 and 4.")

        await self._send(f"x2 {source!s}", fast_polling=True)

    async def x2(self, three_phases: bool) -> None:
        """Set x2 output for phase switching.

        Args:
            three_phases (bool): True for using all three phases, False for using only one phase.

        """
        if not self.device_info.phase_switch_x2:
            raise NotImplementedError("x2 is not available for the given charging station")

        if not isinstance(three_phases, bool):
            raise ValueError("X2 output parameter must be True or False.")

        await self._send(f"x2 {three_phases!s}", fast_polling=True)

    async def set_charging_power(  # noqa: PLR0912, PLR0915
        self,
        power: int | float,
        round_up: bool = False,
        stop_below_6_A: bool = True,  # noqa: N803
    ) -> bool:
        """Set charging power.

        For this command you have to authorize a charging process first. Afterwards the charging
        power can be adjusted. The given power is the maximum power, current values are rounded down
        by default to not overshoot this power value. This function is still experimental.

        Args:
            power (int | float): charging power in kW.
            round_up (bool, optional): _description_. Defaults to False.
            stop_below_6_A (bool, optional): wether to stop below 6A. Defaults to True.

        Returns:
            bool: _description_

        """
        if not self.device_info.is_meter_integrated():
            raise NotImplementedError(
                "set_charging_power only available in charging stations with integrated meter"
            )

        if not isinstance(power, int | float):
            raise ValueError("Power must be int or float.")

        if power < 0 or power > 44.0:
            raise ValueError("Power must be between 0 and 44 kW.")

        # Abort if there is no authorized charging process
        if self.get_value(ReportField.AUTHREQ) == 1:
            _LOGGER.warning("Charging station is not authorized. Please authorize first")
            return False

        if not self.get_value("State_on"):
            _LOGGER.info("Charging process is authorized but stopped. Trying to enable it")
            self._charging_started_event.clear()
            await self.set_ena(True)
            try:
                await asyncio.wait_for(self._charging_started_event.wait(), timeout=10)
            except TimeoutError:
                _LOGGER.warning("Charging process could not be started after 10 seconds. Abort")
                return False

        # Identify the number of phases and calculate average voltage of active phases
        number_of_phases = 0
        avg_voltage = 0.0
        try:
            p1 = self.get_value(ReportField.I1) * self.get_value(ReportField.U1)
            p2 = self.get_value(ReportField.I2) * self.get_value(ReportField.U2)
            p3 = self.get_value(ReportField.I3) * self.get_value(ReportField.U3)
            _LOGGER.debug(
                "set_charging_power measurements:\n"
                + "phase 1: %d, %d, %d \n"
                + "phase 2: %d, %d, %d \n"
                + "phase 3: %d, %d, %d",
                p1,
                self.get_value(ReportField.I1),
                self.get_value(ReportField.U1),
                p2,
                self.get_value(ReportField.I2),
                self.get_value(ReportField.U2),
                p3,
                self.get_value(ReportField.I3),
                self.get_value(ReportField.U3),
            )

            min_power = 2
            if p1 > min_power:
                number_of_phases += 1
                avg_voltage += self.get_value(ReportField.U1)
            if p2 > min_power:
                number_of_phases += 1
                avg_voltage += self.get_value(ReportField.U2)
            if p3 > min_power:
                number_of_phases += 1
                avg_voltage += self.get_value(ReportField.U3)

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
            _LOGGER.error("Unable to identify number of charging phases")
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
                    _LOGGER.error("Calculated current is much too high, something wrong")
                    return False
        except ValueError:
            _LOGGER.error("Could not set calculated current.")

        return True
