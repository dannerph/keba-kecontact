"""Tests for connection host resolution and socket lifecycle."""

import asyncio
import json
import socket
from collections.abc import Generator
from unittest.mock import AsyncMock, patch

import pytest

from keba_kecontact.connection import KebaKeContact, SetupError
from keba_kecontact.const import KebaResponse


@pytest.fixture(autouse=True)
def reset_singleton() -> Generator[None]:
    """Give each test an independent connection."""
    KebaKeContact._instance = None
    yield
    KebaKeContact._instance = None


def test_hostname_resolves_to_response_address() -> None:
    """Match the response IP to the resolved hostname."""

    async def run() -> None:
        loop = asyncio.get_running_loop()
        connection = KebaKeContact(loop, timeout=1)
        report = {
            "ID": "1",
            "Product": "KC-P30-EC220112-000-DE",
            "Serial": "123456789",
            "Firmware": "1",
        }

        async def send(host: str, payload: str) -> None:
            assert host == "127.0.0.1"
            assert payload == "report 1"
            await connection._internal_callback(json.dumps(report).encode(), (host, 7090))

        with (
            patch.object(
                loop,
                "getaddrinfo",
                new=AsyncMock(
                    return_value=[(socket.AF_INET, socket.SOCK_DGRAM, 17, "", ("127.0.0.1", 7090))]
                ),
            ),
            patch.object(connection, "send", side_effect=send),
        ):
            station = await connection.setup_charging_station(
                "wallbox.local", periodic_request=False
            )
        assert station.device_info.host == "127.0.0.1"
        assert connection.get_charging_station("127.0.0.1") is station
        assert connection.get_charging_station("wallbox.local") is station
        assert not connection._waiting_list
        connection.remove_charging_station("wallbox.local")
        assert connection.get_charging_station("127.0.0.1") is None
        assert not connection._host_aliases

    asyncio.run(run())


def test_unresolvable_host() -> None:
    """Report a DNS lookup failure as a setup error."""

    async def run() -> None:
        loop = asyncio.get_running_loop()
        connection = KebaKeContact(loop, timeout=1)
        with (
            patch.object(loop, "getaddrinfo", new=AsyncMock(side_effect=socket.gaierror)),
            pytest.raises(SetupError, match="Could not resolve host"),
        ):
            await connection.setup_charging_station("invalid.local")

    asyncio.run(run())


def test_timeout_removes_pending_request() -> None:
    """Do not leave a response listener after a timeout."""

    async def run() -> None:
        connection = KebaKeContact(asyncio.get_running_loop(), timeout=0)
        with patch.object(connection, "send", new=AsyncMock()), pytest.raises(SetupError):
            await connection.get_device_info("127.0.0.1")
        assert (KebaResponse.REPORT_1, "127.0.0.1") not in connection._waiting_list

    asyncio.run(run())


def test_close_stops_listener_and_allows_rebind() -> None:
    """Close the socket without leaving a pending receive task."""

    async def run() -> None:
        connection = KebaKeContact(asyncio.get_running_loop(), timeout=1)
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        with patch("keba_kecontact.connection.UDP_PORT", port):
            await connection.init_socket("127.0.0.1")
            listener = connection._listen_task
            await asyncio.sleep(0)
            connection.close()
            await asyncio.sleep(0)
            assert listener.cancelled()
            await connection.init_socket("127.0.0.1")
            new_listener = connection._listen_task
            connection.close()
            await asyncio.sleep(0)
            assert new_listener.cancelled()

    asyncio.run(run())
