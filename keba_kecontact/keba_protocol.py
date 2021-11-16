#!/usr/bin/python3

import asyncio
import logging
import json
import datetime

_LOGGER = logging.getLogger(__name__)


class KebaProtocol(asyncio.DatagramProtocol):
    """Representation of a KEBA charging station connection protocol."""

    data = {}

    def __init__(self, callback):
        self._transport = None
        self._callback = callback

    def connection_made(self, transport):
        """Request base information after initial connection created."""
        self._transport = transport
        _LOGGER.debug("Asyncio UDP connection setup complete.")

    def error_received(self, exc):
        """Log error after receiving."""
        _LOGGER.error("Error received: %s", exc)

    def connection_lost(self, exc):
        """Set state offline if connection is lost."""
        _LOGGER.error("Connection lost.")
        self.data['Online'] = False

    def datagram_received(self, data, addr):
        """Handle received datagram."""
        _LOGGER.debug("Datagram received.")
        self.data['Online'] = True
        decoded_data = data.decode()

        if 'TCH-OK :done' in decoded_data:
            _LOGGER.debug("Command accepted: %s", decoded_data.rstrip())
            return True

        if 'TCH-ERR' in decoded_data:
            _LOGGER.warning("Command rejected: %s", decoded_data.rstrip())
            return False

        json_rcv = json.loads(data.decode())

        # Prepare received data
        if 'ID' in json_rcv:
            if json_rcv['ID'] == '1':
                try:
                    # Prettify uptime
                    secs = json_rcv['Sec']
                    json_rcv['uptime_pretty'] = str(datetime.timedelta(seconds=secs))

                    # Extract product version
                    product_string = json_rcv['Product']
                    if "P30" in product_string:
                        json_rcv['Product'] = "KEBA P30"
                    elif "P20" in product_string:
                        json_rcv['Product'] = "KEBA P20"
                    elif "BMW" in product_string:
                        json_rcv['Product'] = "BMW Wallbox"
                    self.data.update(json_rcv)
                except KeyError:
                    _LOGGER.warning("Could not extract report 1 data for KEBA charging station")
                return True
            elif json_rcv['ID'] == '2':
                try:
                    json_rcv['Max curr'] = json_rcv['Max curr'] / 1000.0
                    json_rcv['Curr HW'] = json_rcv['Curr HW'] / 1000.0
                    json_rcv['Curr user'] = json_rcv['Curr user'] / 1000.0
                    json_rcv['Curr FS'] = json_rcv['Curr FS'] / 1000.0
                    json_rcv['Curr timer'] = json_rcv['Curr timer'] / 1000.0
                    json_rcv['Setenergy'] = round(json_rcv['Setenergy'] / 10000.0, 2)

                    # Extract plug state
                    plug_state = json_rcv['Plug']
                    json_rcv['Plug_plugged'] = plug_state > 3
                    json_rcv["Plug_wallbox"] = plug_state > 0
                    json_rcv["Plug_locked"] = plug_state == 3 | plug_state == 7
                    json_rcv["Plug_EV"] = plug_state > 4

                    # Extract charging state
                    state = json_rcv['State']
                    json_rcv['State_on'] = state == 3
                    if state is not None:
                        switcher = {
                            0: "starting",
                            1: "not ready for charging",
                            2: "ready for charging",
                            3: "charging",
                            4: "error",
                            5: "authorization rejected"
                        }
                        json_rcv['State_details'] = switcher.get(
                            state, "State undefined")

                    # Extract failsafe details
                    json_rcv['FS_on'] = json_rcv['Tmo FS'] > 0
                    self.data.update(json_rcv)
                except KeyError:
                    _LOGGER.warning("Could not extract report 2 data for KEBA charging station")
                return True
            elif json_rcv['ID'] == '3':
                try:
                    json_rcv['I1'] = json_rcv['I1'] / 1000.0
                    json_rcv['I2'] = json_rcv['I2'] / 1000.0
                    json_rcv['I3'] = json_rcv['I3'] / 1000.0
                    json_rcv['P'] = round(json_rcv['P'] / 1000000.0, 2)
                    json_rcv['PF'] = json_rcv['PF'] / 1000.0
                    json_rcv['E pres'] = round(json_rcv['E pres'] / 10000.0, 2)
                    json_rcv['E total'] = round(json_rcv['E total'] / 10000.0, 2)
                    self.data.update(json_rcv)
                except KeyError:
                    _LOGGER.warning("Could not extract report 3 data for KEBA charging station")
            elif json_rcv['ID'] == '100':
                try:
                    json_rcv['E start'] = round(json_rcv['E start'] / 10000.0, 2)
                    json_rcv['E pres'] = round(json_rcv['E pres'] / 10000.0, 2)
                    self.data.update(json_rcv)
                except KeyError:
                    _LOGGER.warning("Could not extract report 100 data for KEBA charging station")
            else:
                _LOGGER.debug("Report ID not known/implemented")
        else:
            _LOGGER.debug("No ID in response from Keba charging station")
            return False

        # Join data to internal data store and send it to the callback function
        _LOGGER.debug("Execute callback")
        self._callback(self.data)

    def send(self, payload):
        """Send data to KEBA charging station."""
        _LOGGER.debug("Send %s", payload)
        self._transport.sendto(payload.encode('cp437', 'ignore'))
