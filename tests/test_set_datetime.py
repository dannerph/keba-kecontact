"""Test set_datetime command."""

import asyncio
from unittest.mock import AsyncMock

from keba_kecontact.charging_station import ChargingStation
from keba_kecontact.charging_station_info import ChargingStationInfo


def test_set_datetime() -> None:
    """Test set_datetime UDP command."""
    report_1 = {
        "ID": "1",
        "Product": "KC-P30-XXXXXXXX-000",
        "Serial": "123456789",
        "Firmware": "some firmware string",
        "COM-module": 0,
        "Sec": 123,
    }

    info = ChargingStationInfo("127.0.0.1", report_1)
    connection = AsyncMock()

    async def run_test() -> None:
        station = ChargingStation(
            connection, info, asyncio.get_running_loop(), periodic_request=False
        )

        await station.set_datetime(1497944434)

    asyncio.run(run_test())

    connection.send.assert_awaited_once_with("127.0.0.1", "setdatetime 1497944434", 0)
