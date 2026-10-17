"""Test charging station report parsing."""

import asyncio
import json
from types import SimpleNamespace

import pytest

from keba_kecontact.charging_station import ChargingStation


@pytest.mark.parametrize(
    ("plug_state", "expected_locked"),
    [
        (0, False),
        (1, False),
        (3, True),
        (5, False),
        (7, True),
    ],
)
def test_datagram_received_decodes_plug_lock_state(
    plug_state: int, expected_locked: bool
) -> None:
    """Decode the plug-lock status from report 2."""

    async def receive_report() -> None:
        station = ChargingStation(
            keba_connection=None,
            device_info=SimpleNamespace(host="127.0.0.1", model="P30"),
            loop=asyncio.get_running_loop(),
            periodic_request=False,
        )

        await station.datagram_received(json.dumps({"ID": "2", "Plug": plug_state}))

        assert station.get_value("Plug_locked") is expected_locked

    asyncio.run(receive_report())
